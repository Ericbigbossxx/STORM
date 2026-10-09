"""Reconstruct the W39 static cockpit from cached workbook values, without live I/O.

The historical compatibility calculation is deliberately separate from source-quality
acceptance. Baseline HTML contributes layout and comparison targets, never metrics.
Business outputs belong in ignored outputs/, never in a Git commit.
"""
from __future__ import annotations
import argparse
import calendar
from collections import defaultdict, Counter
from datetime import date, datetime, timedelta
import hashlib
import html
import json
from pathlib import Path
import re
import openpyxl

CHANNELS = {'Walmart Seller': ('Walmart', 'Walmart / MP'), 'Walmart DSV': ('Walmart', 'Walmart / DSV'), "Lowe's": ("Lowe's", "Lowe's / DS"), 'The Home Depot Inc': ('THD', 'THD / DS'), 'The Home Depot Inc DFC': ('THD', 'THD / DFC')}
COLORS = {'THD / DS':'#F96302','THD / DFC':'#FF9B52',"Lowe's / DS":'#004990','Walmart / MP':'#0071CE','Walmart / DSV':'#00A3E0'}
COSTS = {'cogs':3,'fixed_cost':5,'mkt_insite':6,'mkt_offsite_seed':7,'return_warranty':8,'funding':9,'mkt_channel':10}
KEY_COLUMNS = [17,20,23,19,1]

def clean(x):
    return x.strip() if isinstance(x, str) else x

def parse_date(x):
    if isinstance(x, (int,float)):
        return openpyxl.utils.datetime.from_excel(x).date()
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    for fmt in ('%m/%d/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(x, fmt).date()
        except ValueError:
            pass
    raise ValueError(f'Unsupported date: {x!r}')

def num(x):
    """Historical zero coercion ONLY; every nonnumeric cost is separately audited."""
    return float(x) if isinstance(x, (int,float)) else 0.0

def total(rows, key):
    return round(sum(r[key] for r in rows), 2)

def groups(rows, *keys):
    out = defaultdict(list)
    for row in rows:
        out[tuple(row[k] for k in keys)].append(row)
    return dict(sorted(out.items()))

def ratio(a,b,places=4):
    return round(a/b, places) if b else 0.0

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_source(path, *, strict=False, na_cost_zero=False, review_policy=None):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    actual = list(wb['actual order'].values)
    review_policy = review_policy or {}
    if review_policy and review_policy.get('source_sha256') != digest(path):
        raise ValueError('Reviewed source policy does not match workbook digest')
    for cell, value in review_policy.get('approved_cell_corrections', {}).items():
        col, row = openpyxl.utils.cell.coordinate_from_string(cell)
        values = list(actual[row-1])
        values[openpyxl.utils.column_index_from_string(col)-1] = value
        actual[row-1] = tuple(values)
    excluded_rows = set(review_policy.get('superseded_source_rows', []))
    headers = [clean(x) for x in actual[0]]
    assert headers[17:24] == ['Date','Country','Channel','SKU','Ordered Revenue','Ordered Units','Order Number']
    buckets = defaultdict(list)
    for rownum, raw in enumerate(actual[1:],2):
        if rownum in excluded_rows:
            continue
        if raw[19] not in CHANNELS:
            continue
        r = tuple(clean(x) for x in raw)
        if strict:
            for col in (21,22):
                if not isinstance(r[col],(int,float)):
                    raise ValueError(f'Non-numeric order amount/units at row {rownum}, column {col+1}')
            for col in COSTS.values():
                v=r[col]
                if not isinstance(v,(int,float)) and v!='-' and not (na_cost_zero and v=='#N/A'):
                    raise ValueError(f'Unapproved cost value {v!r} at row {rownum}, column {col+1}')
        if r[15] != 2026 or r[18] != 'US':
            raise ValueError('Unexpected year or market in W39 input')
        buckets[tuple(r[i] for i in KEY_COLUMNS)].append((rownum,r))
    conflicts=[]
    duplicates=[]
    invalid=[]
    rows=[]
    last_rows=[]
    for entries in buckets.values():
        rownum,r=entries[0]
        differing=[i for i in range(1,24) if len({v[i] for _,v in entries})>1]
        if len(entries)>1:
            duplicates.append({'source_rows':[n for n,_ in entries], 'date':parse_date(r[17]).isoformat(), 'sku':r[20], 'channel':r[19], 'revenue':num(r[21]), 'units':num(r[22]), 'extra_rows':len(entries)-1, 'fully_identical':not differing})
        if differing:
            conflicts.append({'source_rows':[n for n,_ in entries], 'fields':[headers[i] for i in differing], 'month':r[16]})
        for output, (n,v) in [(rows,entries[0]),(last_rows,entries[-1])]:
            dt=parse_date(v[17]); platform,channel=CHANNELS[v[19]]
            if dt.year!=v[15] or dt.month!=v[16]:
                raise ValueError(f'Date / year / month mismatch at row {n}')
            record={'source_row':n,'date':dt,'month':dt.month,'sku':v[20], 'platform':platform,'channel':channel,'brand':v[13], 'power':v[12], 'revenue':num(v[21]), 'units':num(v[22]), 'order':v[23]}
            for k,col in COSTS.items():record[k]=num(v[col])
            record['cm']=record['revenue']-sum(record[k] for k in COSTS)
            output.append(record)
        for k,col in COSTS.items():
            if not isinstance(r[col],(int,float)):
                invalid.append({'source_row':rownum,'cell':f'{openpyxl.utils.get_column_letter(col+1)}{rownum}', 'month':r[16], 'metric':k, 'value':r[col], 'revenue':num(r[21])})
    sku_map={clean(r[0]):tuple(clean(v) for v in r[:5]) for r in wb['SKU MAP'].iter_rows(min_row=2,values_only=True) if r[0]}
    unmapped=[]
    for r in rows:
        mapping=sku_map.get(r['sku'])
        r['category']=mapping[4] if mapping and mapping[4] else 'UNKNOWN'
        if r['category']=='UNKNOWN':unmapped.append(r['sku'])
    bp=[]
    for n,r in enumerate(wb['KPI Rawdata'].iter_rows(min_row=2,values_only=True),2):
        if r[3] in CHANNELS and r[5]==2026:
            if not isinstance(r[9],(int,float)):
                raise ValueError(f'Missing BP amount J{n}')
            bp.append({'source_row':n,'sku':clean(r[0]),'month':r[4], 'platform':CHANNELS[r[3]][0], 'brand':clean(r[14]), 'revenue':float(r[9])})
    dfc_rows=list(wb['THD- robot Sell out'].values)
    dfc=[]
    for n,r in enumerate(dfc_rows[1:],2):
        if not r[0] or not r[1]:continue
        if n==len(dfc_rows) and r[0]==r[1] and all(v==0 for v in r[2:7]):continue  # observed blank pivot footer
        dt=parse_date(r[0])
        if any(not isinstance(r[i],(int,float)) for i in [2,3,5]):
            raise ValueError(f'Missing DFC metric at row {n}')
        dfc.append({'date':dt,'month':dt.strftime('%Y-%m'),'sku':clean(r[1]),'units':r[2],'gmv':r[3],'traffic':r[5]})
    inventory={}; legacy_inventory={}
    for n,r in enumerate(dfc_rows[2:],3):
        if r[9] in sku_map and isinstance(r[8],(int,float)):
            inventory[r[9]]=r[8]
            legacy_inventory[r[9]]=r[19]
    wb.close()
    audit={'raw_scope_rows':sum(len(v) for v in buckets.values()),'retained_rows':len(rows), 'removed_rows':sum(len(v)-1 for v in buckets.values()), 'duplicate_groups':sum(len(v)>1 for v in buckets.values()), 'conflicting_groups':len(conflicts), 'conflicts':conflicts, 'duplicates':duplicates, 'nonnumeric_costs':invalid, 'unmapped_skus':sorted(set(unmapped)), 'inventory_source':inventory, 'inventory_legacy_sales_column':legacy_inventory, 'cost_sensitivity':[]}
    for month in sorted({r['month'] for r in rows}):
        first=[r for r in rows if r['month']==month];last=[r for r in last_rows if r['month']==month]
        audit['cost_sensitivity'].append({'month':month,'first_cm':total(first,'cm'),'last_cm':total(last,'cm'),'delta_last_minus_first':round(total(last,'cm')-total(first,'cm'),2)})
    if review_policy:
        audit['source_review'] = review_policy
        audit['superseded_rows_removed'] = len(excluded_rows)
    if strict and conflicts:
        raise ValueError(f'{len(conflicts)} duplicate keys have conflicting values; weekly build requires review')
    return rows,bp,dfc,inventory,audit

def scoped_adjustments(adjustments, months=None, **scope):
    return [v for v in adjustments if (months is None or v['month'] in months) and all(v.get(k)==value for k,value in scope.items())]


def waterfall(rows, adjustments=()):
    v={'gmv':total(rows,'revenue')}
    v.update({k:round(total(rows,k)+sum(a['amount'] for a in adjustments if a['metric']==k),2) for k in COSTS})
    v['gm']=round(v['gmv']-v['cogs'],2)
    v['cm']=round(v['gmv']-sum(v[k] for k in COSTS),2)
    v['cm_pct']=ratio(v['cm'],v['gmv'])
    v['cm_pct_display']=round(v['cm']/v['gmv']*100,1) if v['gmv'] else 0.0
    if adjustments and not v['gmv']:
        v['cm_pct']=v['cm_pct_display']=None
    return v

def sku_changes(first,second,names,count):
    a={k[0]:total(v,'revenue') for k,v in groups(first,'sku').items()};b={k[0]:total(v,'revenue') for k,v in groups(second,'sku').items()}
    out=[]
    for sku in sorted(a.keys()|b.keys()):
        x,y=a.get(sku,0),b.get(sku,0)
        out.append({'sku':sku,names[0]:x,names[1]:y,'change':round(y-x,2),'change_pct':ratio(y-x,x) if x else (1.0 if y else 0.0)})
    return {'growth':sorted(out,key=lambda r:-r['change'])[:count], 'decline':sorted(out,key=lambda r:r['change'])[:count]}

def heatmap(rows):
    return [{'category':k[0],'brand':k[1],'revenue':total(v,'revenue')} for k,v in groups(rows,'category','brand').items()]

def make_period(rows,bp,months,label,mom_months,cutoff, *, weekly=False, cost_adjustments=()):
    r=[v for v in rows if v['month'] in months];plan=[v for v in bp if v['month'] in months]
    start=min(v['date'] for v in r);end=max(v['date'] for v in r)
    week_rows=rows if weekly else r
    w2=[v for v in week_rows if end-timedelta(days=6)<=v['date']<=end]
    w1=[v for v in week_rows if end-timedelta(days=13)<=v['date']<=end-timedelta(days=7)]
    adjustments=scoped_adjustments(cost_adjustments,months)
    wf=waterfall(r,adjustments);rev=wf['gmv'];a,b=total(w1,'revenue'),total(w2,'revenue');wow=ratio(b-a,a)
    cm=wf['cm_pct'];gm=ratio(wf['gm'],rev)
    ex={'total_revenue':rev,'total_units':int(total(r,'units')),'total_orders':len({v['order'] for v in r if v['order'] is not None}), 'wow_change':wow,'wow_display':round(wow*100,1),'w1':a,'w2':b,'cm_pct':cm,'cm_pct_display':round(cm*100,1),'cm_display':round(cm*100,1),'overall_cm_pct':cm,'gm_pct':gm,'gm_pct_display':round(gm*100,1),'gm_display':round(gm*100,1),'avg_daily':round(rev/((end-start).days+1),2)}
    p={'meta':{'label':label,'months':months},'executive':ex}
    p['daily_trend']=[{'date':k[0].isoformat(),'revenue':total(v,'revenue'),'units':int(total(v,'units'))} for k,v in groups(r,'date').items()]
    p['channel_overview']=[{'label':ch,'revenue':total([v for v in r if v['channel']==ch],'revenue'),'share':ratio(total([v for v in r if v['channel']==ch],'revenue'),rev),'w1':total([v for v in w1 if v['channel']==ch],'revenue'),'w2':total([v for v in w2 if v['channel']==ch],'revenue')} for _,ch in CHANNELS.values()]
    waterfall_keys=set(groups(r,'platform','brand'))|{(v['platform'],v['brand']) for v in adjustments}
    p['waterfalls']={'Overall':wf, **{f'{pl} / {brand}':waterfall([v for v in r if v['platform']==pl and v['brand']==brand],scoped_adjustments(adjustments,platform=pl,brand=brand)) for pl,brand in sorted(waterfall_keys)}}
    sw=sku_changes(w1,w2,('w1','w2'),5);p['sku_wow_growth']=sw['growth'];p['sku_wow_decline']=sw['decline']
    p['platform_sku_wow']={pl:sku_changes([v for v in w1 if v['platform']==pl],[v for v in w2 if v['platform']==pl],('w1','w2'),5) for pl in ['THD',"Lowe's",'Walmart']}
    m1=[v for v in rows if v['month']==mom_months[0]];m2=[v for v in rows if v['month']==mom_months[1]]
    mom=sku_changes(m1,m2,('m1','m2'),10);p['mom_growth']=mom['growth'];p['mom_decline']=mom['decline']
    p['platform_mom']={pl:sku_changes([v for v in m1 if v['platform']==pl],[v for v in m2 if v['platform']==pl],('m1','m2'),10) for pl in ['THD',"Lowe's",'Walmart']}
    p['mom_m1_label']=calendar.month_abbr[mom_months[0]];p['mom_m2_label']=calendar.month_abbr[mom_months[1]]
    for target,key,name in [('brand_performance','brand','brand'),('power_source','power','source')]:
        p[target]=[]
        for k,v in groups(r,key).items():
            amount=total(v,'revenue');margin=waterfall(v,scoped_adjustments(adjustments,**{key:k[0]}))['cm'];rate=ratio(margin,amount)
            p[target].append({name:k[0],'revenue':amount,'cm_pct':rate,'cm_display':round(margin/amount*100,1) if amount else 0.0})
    p['brand_cm']={v['brand']:v['cm_display'] for v in p['brand_performance']}
    p['category_brand_heatmap']=heatmap(r)
    p['category_brand_by_platform']={'All':heatmap(r),**{pl:heatmap([v for v in r if v['platform']==pl]) for pl in ['THD',"Lowe's",'Walmart']}}
    p['top_skus']=[]
    for (sku,),v in sorted(groups(r,'sku').items(),key=lambda kv:-total(kv[1],'revenue'))[:10]:
        x=total([v for v in w1 if v['sku']==sku],'revenue');y=total([v for v in w2 if v['sku']==sku],'revenue')
        p['top_skus'].append({'sku':sku,'revenue':total(v,'revenue'),'units':int(total(v,'units')),'brand':v[0]['brand'],'power_source':v[0]['power'],'contribution':ratio(total(v,'revenue'),rev),'platform_breakdown':[{'channel':k[0],'revenue':total(g,'revenue')} for k,g in groups(v,'channel').items()],'wow_change':ratio(y-x,x) if x else (1.0 if y else 0.0),'w1':x,'w2':y})
    p['platform_brand_bp']=[]
    pacing=calendar.monthrange(cutoff.year,cutoff.month)[1]/cutoff.day if months==[cutoff.month] else 1
    for pl,brand in sorted(waterfall_keys):
        v=[x for x in r if x['platform']==pl and x['brand']==brand]
        actual=total(v,'revenue');budget=total([q for q in plan if q['platform']==pl and q['brand']==brand],'revenue');projected=round(actual*pacing,2);att=ratio(projected,budget)
        p['platform_brand_bp'].append({'platform':pl,'brand':brand,'label':f'{pl} / {brand}','actual':actual,'revenue':actual,'bp':budget,'projected':projected,'attainment':att,'att_display':round(projected/budget*100,1) if budget else 0.0})
    def lookup(actual,budget):
        a={k[0]:total(v,'revenue') for k,v in groups(actual,'sku').items()}
        return {k[0]:round(a.get(k[0],0)/total(v,'revenue')*100,1) for k,v in groups(budget,'sku').items() if total(v,'revenue')>0}
    p['bp_att_lookup']={'by_platform':{pl:lookup([v for v in r if v['platform']==pl],[v for v in plan if v['platform']==pl]) for pl in ['THD',"Lowe's",'Walmart']},'by_sku_all':lookup(r,plan)}
    # New factual summaries; historical natural-language advice is not copied.
    p['conclusions']={}
    for pl in ['THD',"Lowe's",'Walmart']:
        pr=[v for v in r if v['platform']==pl];x=total([v for v in w1 if v['platform']==pl],'revenue');y=total([v for v in w2 if v['platform']==pl],'revenue')
        p['conclusions'][pl]=[{'t':'w','x':f'{html.escape(pl)} revenue ${total(pr,"revenue"):,.2f}; share {total(pr,"revenue")/rev*100:.1f}%.'},{'t':'w','x':f'7-day revenue: ${x:,.2f} to ${y:,.2f}; change {(y/x-1)*100:.1f}%.' if x else '7-day change: UNKNOWN (prior revenue is zero).'}, {'t':'w','x':'CM figures reproduce historical handling only. Cost gaps and duplicate-row conflicts remain unapproved.'}]
    return p

def make_dfc(rows,inventory):
    def summary(r):
        g=total(r,'gmv');u=int(total(r,'units'));t=int(total(r,'traffic'))
        return {'gmv':g,'units':u,'traffic':t,'conv_rate':ratio(u,t,6)}
    months=groups(rows,'month');out={'monthly_summary':{},'daily_by_month':{},'sku_by_month':{},'inventory':inventory,'available_months':[k[0] for k in months]}
    for (m,),r in months.items():
        out['monthly_summary'][m]=summary(r)
        out['daily_by_month'][m]=[{'date':k[0].isoformat(),**summary(v)} for k,v in groups(r,'date').items()]
        out['sku_by_month'][m]=[{'sku':k[0],**summary(v),'asp':round(sum(q['gmv'] for q in v)/sum(q['units'] for q in v),2) if sum(q['units'] for q in v) else 0.0} for k,v in groups(r,'sku').items()]
    out['ytd_gmv']=total(rows,'gmv');out['aug_gmv']=total([r for r in rows if r['month'].endswith('-08')],'gmv')
    return out

def compare(a,b,path='',result=None):
    if result is None:result={'matches':0,'differences':[]}
    if path.endswith('/conclusions'):return result
    if isinstance(a,dict) and isinstance(b,dict):
        for k in sorted(a.keys()|b.keys()):
            if k not in a or k not in b:result['differences'].append({'path':path+'/'+k,'old':a.get(k),'new':b.get(k)})
            else:compare(a[k],b[k],path+'/'+k,result)
    elif isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b):result['differences'].append({'path':path+'/length','old':len(a),'new':len(b)})
        for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+'/'+str(i),result)
    elif a==b or isinstance(a,(int,float)) and isinstance(b,(int,float)) and abs(a-b)<1e-7:result['matches']+=1
    else:result['differences'].append({'path':path,'old':a,'new':b})
    return result

def write_preview(template,data,baseline,audit,output):
    """Reuse the old layout, replacing its entire data payload with source calculations."""
    rows=[]
    for name in data['period_keys']:
        old=baseline['periods'][name]['waterfalls']['Overall'];new=data['periods'][name]['waterfalls']['Overall']
        equal=all(old[k]==new[k] for k in old if k not in ('cm_pct_display',))
        rows.append(f"<tr><td>{name}</td><td>${old['gmv']:,.2f}</td><td>${new['gmv']:,.2f}</td><td>${old['cm']:,.2f}</td><td>${new['cm']:,.2f}</td><td>{'一致' if equal else '有差异'}</td></tr>")
    inventory_rows=''.join(f"<tr><td>{html.escape(sku)}</td><td>{audit['inventory_legacy_sales_column'][sku]}</td><td>{value}</td><td>旧值对应 T 列累计销量；原始库存来自 I 列</td></tr>" for sku,value in audit['inventory_source'].items())
    errors=[v for v in audit['nonnumeric_costs'] if v['value']=='#N/A']
    dash=[v for v in audit['nonnumeric_costs'] if v['metric']=='cogs' and v['value']=='-']
    september=[v for v in errors if v['month']==9]
    sensitivity=next(v for v in audit['cost_sensitivity'] if v['month']==9)
    walmart_bp=next(v for v in data['periods']['Sep MTD']['platform_brand_bp'] if v['platform']=='Walmart' and v['brand']=='Sunseeker')['bp']
    diffs=audit['comparison']['differences']
    diff_rows=''.join(f"<tr><td style='white-space:normal;overflow-wrap:anywhere'>{html.escape(d['path'])}</td><td>{html.escape(str(d['old']))}</td><td>{html.escape(str(d['new']))}</td></tr>" for d in diffs)
    report=f"""
<div id="p-reproduction" class="panel on" style="line-height:1.65">
  <div class="card"><h2 style="font-size:20px">W39 复现核验</h2>
  <p>从 9.22 Excel 重新计算。订单数据截至 {audit['data_through']}，THD sell-out 截至 {audit['dfc_data_through']}。已恢复六个时间维度的收入、费用、WoW、品牌、SKU 和 DFC 销售计算；这不是利润口径的最终验收。</p>
  <p>原始文件、历史看板均保留。本页为本地复现预览，未发布。页面沿用原布局，全部数值由源表计算；旧看板只用于布局及差异核对。</p></div>
  <div class="card"><h3>核心金额对比（USD）</h3><p>下列 CM 为历史处理口径：去重保留首行，非数字成本按零参与复算。真实成本和冲突行尚未核准，CM 状态为 UNKNOWN。复现一致不代表利润正确。</p>
  <div style="overflow-x:auto"><table><thead><tr><th>期间</th><th>旧收入</th><th>复算收入</th><th>旧 CM</th><th>历史口径复算 CM</th><th>金额核对</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>
  <div class="card"><h3>影响后续更新的事项</h3><ol style="padding-left:22px">
  <li><b>成本缺失：</b>去重后 COGS 有 {len(errors)} 条 #N/A（9 月 {len(september)} 条，对应收入 ${sum(v['revenue'] for v in september):,.2f}），另有 {len(dash)} 条“-”。不能把历史零值处理当作已确认成本。缺失明细保留源单元格位置。</li>
  <li><b>去重费用冲突：</b>{audit['raw_scope_rows']:,} 行范围内数据按 Date + SKU + Order Number + Channel + Cost Type 保留首行后剩 {audit['retained_rows']:,} 行，共排除 {audit['removed_rows']:,} 行；其中 {audit['conflicting_groups']:,} 组费用不一致。9 月取最后一条的 CM 为 ${sensitivity['last_cm']:,.2f}，取第一条为 ${sensitivity['first_cm']:,.2f}，差额 ${sensitivity['delta_last_minus_first']:,.2f}。两种选择均未获得业务确认。</li>
  <li><b>BP 差异：</b>KPI Rawdata 中 Walmart / Sunseeker 的 9 月计划收入合计 ${walmart_bp:,.0f}，旧看板为 0。预览按当前源表展示，排除该计划的历史依据 UNKNOWN；需确认当时是否有人工排除决定。独立试算排除该组合后，{audit['bp_exclusion_hypothesis']['matches']} 项 BP 对比全部一致；这只证明能还原处理方式，不证明排除决定已获批准。</li>
  <li><b>库存列：</b>预览读取源表 Inventory 列，旧看板误对应累计销量。下表逐 SKU 展示差异。Inventory 独立时点未在源表明确标记，不能把它当作任意历史月份月末库存。</li>
  <li><b>利润瀑布图：</b>旧图计算最终柱时未扣 Funding，尽管明细金额已扣。复现预览增加 Funding 柱，使 Q1、Q2、YTD 的图形与金额一致。</li>
  <li><b>历史比较口径：</b>Q3 的 MoM 为 Jul vs Aug，Sep MTD / YTD 为 Aug vs Sep；后者比较整月与部分月，不能等同等长增长率。WoW 保持期末 7 天对前 7 天；图内 W1 / W2 日期随所选期间显示。</li>
  </ol><p>下一步：由业务 Owner（你）确认冲突费用的权威版本、缺失成本补齐方式及 Walmart / Sunseeker BP 范围；DDL 待确认。验收标准：成本缺口有证据、去重规则可重复、BP 范围明确，再验收正式周更。</p></div>
  <div class="card"><h3>THD 库存修正（单位：件）</h3><table><thead><tr><th>SKU</th><th>旧看板</th><th>源表 Inventory</th><th>核对依据</th></tr></thead><tbody>{inventory_rows}</tbody></table></div>
  <div class="card"><h3>来源及范围</h3><p>文件：{html.escape(audit['source']['file'])}。Actual order A:X 用于订单及成本；KPI Rawdata A:AJ 用于 BP；SKU MAP A:E 用于分类；THD- robot Sell out A:G 用于销量及流量、I:J 用于库存映射。</p>
  <p>本次发现最新文件已有 1–9 月订单及成本，因此无需拼接旧文件或 cost detail。仅读取 Excel 已保存值，未重算原文件公式。</p><p>文件 SHA256：<code style="overflow-wrap:anywhere">{audit['source']['sha256']}</code></p>
  <p>旧 Conclusions 的自然语言建议未作为复现目标；此页 Conclusions 仅由已计算数据生成事实摘要。并列名次改为 SKU 稳定排序，因此同额排名可能不同。百分比及 ASP 个别最末位舍入差异保留在下方。</p>
  <details><summary>逐字段对比：{audit['comparison']['matches']:,} 项相同，{len(diffs)} 项差异（含新增 BP、库存修正、并列排序和舍入）</summary><div style="overflow-x:auto"><table><thead><tr><th>位置</th><th>旧值</th><th>复算值</th></tr></thead><tbody>{diff_rows}</tbody></table></div></details>
  </div>
</div>
"""
    payload=json.dumps(data,ensure_ascii=False).replace('</','<\\/')
    preview=re.sub(r'^var DATA = .*;$',lambda _: 'var DATA = '+payload+';',template,flags=re.M)
    preview=re.sub(r'<h1>.*?</h1>','<h1>STORM · W39 复现预览</h1>',preview,count=1)
    preview=preview.replace('<button class="on" data-p="overview">Overview</button>','<button class="on" data-p="reproduction">复现核验</button><button data-p="overview">Overview</button>')
    preview=preview.replace('id="p-overview" class="panel on"','id="p-overview" class="panel"')
    preview=preview.replace('<div class="kpi-strip" id="kpis"></div>','<div class="card" style="border-left:4px solid #d97706;margin:12px 0;line-height:1.6">本地复现预览 · CM 为历史口径复算，状态 UNKNOWN，待成本核准；BP 与库存按源表展示。详见「复现核验」。</div><div class="kpi-strip" id="kpis"></div>')
    preview=preview.replace('<div id="p-conclusions" class="panel"></div>', '<div id="p-conclusions" class="panel"></div>'+report)
    preview=preview.replace("c:ex.overall_cm_pct>=0.05?'green':'red'", "c:'neutral'")
    preview=preview.replace("{l:'GROSS MARGIN%',v:ex.gm_display+'%',s:fmt$(ex.total_revenue*ex.gm_pct),c:'green'}", "{l:'GM% (historical, UNKNOWN)',v:ex.gm_display+'%',s:fmt$(ex.total_revenue*ex.gm_pct),c:'neutral'}")
    preview=preview.replace("color:'#81C784'", "color:'#94a3b8'")
    preview=preview.replace("{l:'CM%'", "{l:'CM% (historical, UNKNOWN)'")
    preview=preview.replace("color:b.cm_display>=5?'#34C759':'#FF3B30'", "color:'#94a3b8'")
    preview=preview.replace("color:p.cm_display>=5?'#34C759':'#FF3B30'", "color:'#94a3b8'")
    preview=preview.replace("{name:'CM (Net)',isSum:true,color:w.cm>=0?'#4CAF50':'#F44336'}", "{name:'Funding',y:-(w.funding||0),color:'#FF9800'},{name:'CM (historical)',isSum:true,color:'#94a3b8'}")
    preview=preview.replace("'CM% = '+w.cm_pct_display+'%'", "'Historical CM% = '+w.cm_pct_display+'% (UNKNOWN until cost review)'")
    preview=preview.replace("dfcS.value=DATA.shared.dfc.available_months[0];", "dfcS.value=DATA.shared.dfc.available_months[DATA.shared.dfc.available_months.length-1];")
    preview=preview.replace('<th>Inventory</th>','<th>Inventory (source snapshot)</th>')
    # Labels are derived from the selected period, rather than fixed current-week text.
    preview=preview.replace("title:{text:'WoW Revenue (7-Day)'}", "title:{text:'WoW Revenue (7-Day)'},subtitle:{text:P.reproduction.w1+' vs '+P.reproduction.w2}")
    (output/'index.html').write_text(preview,encoding='utf-8')


def approved_weekly_bp(bp):
    """Human-confirmed scope takes precedence over raw planning entries."""
    return [v for v in bp if (v['platform'],v['brand'])!=('Walmart','Sunseeker')]


def apply_weekly_sku_bp_scope(p,rows,bp):
    # SKU aggregate attainment compares only platform/brand/SKU cells with a target.
    plan=[v for v in bp if v['month'] in p['meta']['months']]
    keys={(v['platform'],v['brand'],v['sku']) for v in plan if v['revenue']>0}
    actual=[v for v in rows if v['month'] in p['meta']['months'] and (v['platform'],v['brand'],v['sku']) in keys]
    def att_lookup(ar,br):
        return {k[0]:round(total([v for v in ar if v['sku']==k[0]],'revenue')/total(g,'revenue')*100,1) for k,g in groups(br,'sku').items() if total(g,'revenue')>0}
    p['bp_att_lookup']={'by_sku_all':att_lookup(actual,plan),'by_platform':{pl:att_lookup([v for v in actual if v['platform']==pl],[v for v in plan if v['platform']==pl]) for pl in ['THD',"Lowe's",'Walmart']}}


def review_monthly_source(path,rows,cutoff, review_policy=None):
    """Cross-check detail against separately saved summaries; retain disagreements."""
    review_policy=review_policy or {}
    adjustments=review_policy.get('monthly_cost_adjustments',[])
    wb=openpyxl.load_workbook(path,read_only=True,data_only=True)
    actual=list(wb['actual order'].values)
    current=[v for v in rows if v['month']==cutoff.month]
    unit_checks=[]
    for v in current:
        raw=actual[v['source_row']-1]
        if isinstance(raw[2],(int,float)) and isinstance(raw[3],(int,float)):
            delta=round(raw[2]*raw[22]-raw[3],2)
            unit_checks.append({'row':v['source_row'],'delta':delta})
    mismatches=[v for v in unit_checks if abs(v['delta'])>.02]
    if mismatches:raise ValueError('Unit cost times quantity differs from Cost/ALL; review required')
    mapping={'GMV':'revenue','Fixed Cost':'fixed_cost','MKT-Insite':'mkt_insite','MKT-Offsite(Channel MKT)':'mkt_channel','Return+Warranty':'return_warranty','Funding':'funding'}
    comparisons=[]
    for n,raw in enumerate(wb['2026 acutal cost'].values,1):
        if raw[1] not in CHANNELS or raw[0] not in mapping:continue
        detail=[v for v in current if v['channel']==CHANNELS[raw[1]][1] and v['brand']==raw[2]]
        value=raw[cutoff.month+4]
        if not isinstance(value,(int,float)):raise ValueError('Missing monthly cost summary')
        amount=round(total(detail,mapping[raw[0]])+sum(v['amount'] for v in scoped_adjustments(adjustments,[cutoff.month],channel=CHANNELS[raw[1]][1],brand=raw[2]) if v['metric']==mapping[raw[0]]),2);delta=round(amount-value,2)
        tolerance=.5+.005*len(detail)  # whole-dollar summary vs cent-rounded order allocations
        comparisons.append({'cell':f"{openpyxl.utils.get_column_letter(cutoff.month+5)}{n}",'channel':raw[1],'brand':raw[2],'metric':mapping[raw[0]],'summary':value,'detail':amount,'delta':delta,'rounding_tolerance':round(tolerance,3),'within_rounding':abs(delta)<=tolerance})
    for check in comparisons:
        exception=review_policy.get('known_monthly_source_differences',{}).get(check['cell'])
        check['reviewed_source_difference']=bool(exception and exception['summary']==check['summary'] and abs(exception['detail']-check['detail'])<.01)
    if any(not v['within_rounding'] and not v['reviewed_source_difference'] for v in comparisons):
        raise ValueError('Monthly cost summary differs beyond order allocation rounding')
    warehouse=[r[cutoff.month+4] for r in wb['2026 acutal cost'].values if r[0]=='Warehouse+Shipping' and r[1] in CHANNELS]
    if not warehouse or any(v!=0 for v in warehouse):
        raise ValueError('Nonzero or unknown Warehouse+Shipping requires a separate cost mapping')
    overview=list(wb['over view'].values)
    overview_diffs=[]
    # These rows are the saved Sep MTD panel, not a recalculated workbook.
    if clean(overview[1][1])==calendar.month_abbr[cutoff.month] and clean(overview[2][1])=='MTD':
        for col,ch,brand in [(6,'THD / DS','Sunseeker'),(7,'THD / DFC','Sunseeker'),(9,"Lowe's / DS",'Sunseeker'),(10,'Walmart / MP','Sunseeker'),(12,'THD / DS','Badger'),(13,"Lowe's / DS",'Badger'),(14,'Walmart / MP','Badger'),(15,'Walmart / DSV','Badger')]:
            detail=[v for v in current if v['channel']==ch and v['brand']==brand]
            for row,metric in [(81,'revenue'),(83,'cogs'),(106,'cm')]:
                value=overview[row][col];amount=total(detail,metric)
                if abs(amount-value)>2:
                    overview_diffs.append({'cell':f'{openpyxl.utils.get_column_letter(col+1)}{row+1}','channel':ch,'brand':brand,'metric':metric,'overview':value,'detail':amount,'delta':round(amount-value,2)})
    zero=[v for v in current if v['cogs']==0 and v['revenue']!=0]
    zero_groups=[{'platform':k[0],'brand':k[1],'sku':k[2],'revenue':total(v,'revenue'),'rows':[r['source_row'] for r in v]} for k,v in groups(zero,'platform','brand','sku').items()]
    wb.close()
    return {'unit_cost_checks':len(unit_checks),'unit_cost_mismatches':mismatches,'monthly_cost_checks':comparisons,'overview_differences':overview_diffs,'zero_cogs_revenue':total(zero,'revenue'),'zero_cogs_groups':zero_groups,'warehouse_shipping':0}


def weekly_definitions(cutoff):
    """Keep the established MTD / prior month / quarters / YTD presentation."""
    m=cutoff.month
    if m<2:
        raise ValueError('January rollover requires an explicit prior-year source contract')
    current=calendar.month_abbr[m]+(' MTD' if cutoff.day<calendar.monthrange(cutoff.year,m)[1] else '')
    defs=[(current,[m],(m-1,m)),(calendar.month_abbr[m-1],[m-1],(max(1,m-2),m-1))]
    quarter=(m-1)//3+1
    for q in range(quarter,max(0,quarter-3),-1):
        months=list(range((q-1)*3+1,min(q*3,m)+1))
        last=months[-1]
        if q==quarter and cutoff.day<calendar.monthrange(cutoff.year,m)[1] and len(months)>1:
            last-=1  # preserve the prior full-month comparison for an incomplete quarter
        defs.append((f'Q{q}',months,(max(1,last-1),last)))
    defs.append(('YTD',list(range(1,m+1)),(m-1,m)))
    return defs

def prepare_weekly_period(p,rows,cutoff,cost_adjustments=()):
    """Weekly prose and chart dates use this source only; no old narrative is reused."""
    end=date.fromisoformat(p['daily_trend'][-1]['date'])
    wf=p['waterfalls']['Overall'];ex=p['executive']
    ex['cm_display']=ex['cm_pct_display']=wf['cm_pct_display']
    ex['gm_display']=ex['gm_pct_display']=round(wf['gm']/wf['gmv']*100,1) if wf['gmv'] else 0.0
    ex['wow_display']=round((ex['w2']/ex['w1']-1)*100,1) if ex['w1'] else 0.0
    p['reproduction']={'cm_status':'CALCULATED_WITH_APPROVED_ZERO_COST_POLICY',
        'w1':f'{end-timedelta(days=13)} to {end-timedelta(days=7)}',
        'w2':f'{end-timedelta(days=6)} to {end}'}
    if p['mom_m2_label']==calendar.month_abbr[cutoff.month] and cutoff.day<calendar.monthrange(cutoff.year,cutoff.month)[1]:
        p['mom_m2_label']+=' MTD'
    for first,second in [('sku_wow_growth','sku_wow_decline'),('mom_growth','mom_decline')]:
        p[first]=[v for v in p[first] if v['change']>0]
        p[second]=[v for v in p[second] if v['change']<0]
    for field in ['platform_sku_wow','platform_mom']:
        for v in p[field].values():
            v['growth']=[x for x in v['growth'] if x['change']>0]
            v['decline']=[x for x in v['decline'] if x['change']<0]
    p['conclusions']={}
    scoped=[v for v in rows if v['month'] in p['meta']['months']]
    adjustments=scoped_adjustments(cost_adjustments,p['meta']['months'])
    for pl in ['THD',"Lowe's",'Walmart']:
        pr=[v for v in scoped if v['platform']==pl]
        block={'revenue':total(pr,'revenue'),'cm':waterfall(pr,scoped_adjustments(adjustments,platform=pl))['cm'],'brands':[]}
        for brand in ['Badger','Sunseeker']:
            r=[v for v in pr if v['brand']==brand];brand_adjustments=scoped_adjustments(adjustments,platform=pl,brand=brand);w=waterfall(r,brand_adjustments)
            week_rows=[v for v in rows if v['platform']==pl and v['brand']==brand]
            first=[v for v in week_rows if end-timedelta(days=13)<=v['date']<=end-timedelta(days=7)]
            second=[v for v in week_rows if end-timedelta(days=6)<=v['date']<=end]
            x=total(first,'revenue');y=total(second,'revenue')
            budget=next((v for v in p['platform_brand_bp'] if v['platform']==pl and v['brand']==brand),None)
            if budget:
                budget['target_status']='SET' if budget['bp']>0 else 'NOT_SET'
                if budget['bp']<=0:
                    budget['attainment']=budget['att_display']=None
            fees={'退货 / 质保':w['return_warranty'],'固定费用':w['fixed_cost'],'营销费用':w['mkt_insite']+w['mkt_offsite_seed']+w['mkt_channel'],'Funding':w['funding']}
            fee=max(fees,key=fees.get)
            if w['cm']<0:
                finding=f"贡献利润为负；{fee}是 GM 到 CM 的最大扣减项（${fees[fee]:,.0f}）。"
                action=f"优先核查{fee}的明细与归属期间，再评估当前销售的贡献利润。"
            if brand_adjustments and not r:
                finding='本期无订单收入；已确认发生的月度费用仍扣入贡献利润。'
                action='复核营销投放效果及无销售期间的费用支出。'
            elif w['cm']>=0:
                finding=f"贡献利润为正；{fee}扣减 ${fees[fee]:,.0f}。"
                action='优先复盘本周收入下降的 SKU，核查销量、价格与库存变化。' if x and y<x else '跟踪重点 SKU 的销售及费用变化，保持贡献利润。'
            zero=total([v for v in r if v['cogs']==0],'revenue')
            if zero>0:finding+=f" 其中 ${zero:,.0f} 收入对应源表零 COGS。"
            if pl=='Walmart' and brand=='Sunseeker':action='未设 BP，不评价目标达成；优先核查退货 / 质保对贡献利润的影响。'
            movers=sku_changes(first,second,('w1','w2'),1)
            decline=next((v for v in movers['decline'] if v['change']<0),None)
            block['brands'].append({'brand':brand,'has_data':bool(r) or bool(brand_adjustments),'waterfall':w,'w1':x,'w2':y,'wow':round((y/x-1)*100,1) if x else None,'bp':budget,'finding':finding,'action':action,'decline':decline})
        p['conclusions'][pl]=block


def write_weekly_preview(template,data,audit,output):
    cutoff=date.fromisoformat(audit['data_through']);week=f'W{cutoff.isocalendar().week:02d}'
    bp=next((v for v in data['periods'][data['period_keys'][0]]['platform_brand_bp'] if v['platform']=='Walmart' and v['brand']=='Sunseeker'),None)
    dup_rows=''.join(f"<tr><td>{', '.join(map(str,d['source_rows']))}</td><td>{d['date']}</td><td>{html.escape(d['channel'])}</td><td>{html.escape(d['sku'])}</td><td>${d['revenue']:,.2f}</td><td>{d['extra_rows']}</td></tr>" for d in audit['duplicates'])
    prior=audit.get('previous_source_comparison')
    revision=''
    if prior:
        revision=f"<p>与上期源文件的相同截止日（{prior['through']}）比较：该截止月份收入从 ${prior['old_revenue']:,.2f} 修订为 ${prior['current_revenue']:,.2f}，差额 ${prior['revenue_revision']:,.2f}。本周 WoW 使用新版文件内的两段 7 天数据，不用两版累计数相减。</p>"
    current_duplicates=sum(d['extra_rows'] for d in audit['duplicates'] if date.fromisoformat(d['date']).month==cutoff.month)
    zero_count=sum(v['value']=='#N/A' for v in audit['nonnumeric_costs'])
    bp_note='Walmart / Sunseeker 未设 BP（用户确认；over view!K115 为 0）。KPI Rawdata 的相关计划明细不作为有效目标，销售仍计入经营结果；平台、品牌与 SKU 均不计算该组合达成率。'
    excluded=[v for v in audit['bp_excluded_raw_rows'] if v['month']==cutoff.month]
    bp_note+=f" 原误用的本月金额 ${total(excluded,'revenue'):,.2f} 来自 KPI Rawdata 的 {len(excluded)} 条计划行（例如 J{excluded[0]['source_row']}），现已排除；原始明细保留。" if excluded else ''
    notes=f"""<div id="p-source-notes" class="panel" style="line-height:1.65">
<div class="card"><h2 style="font-size:20px">{week} 数据口径</h2>
<p>源文件：{html.escape(audit['source']['file'])}。订单截止 {audit['data_through']}；THD sell-out 截止 {audit['dfc_data_through']}。金额单位 USD。仅包括 THD、Lowe's、Walmart；保留原有品牌及渠道划分。</p>
<p><b>成本：</b>按用户 2026-09-29 确认，成本 #N/A 按 0，原因是这些 SKU 计入销售但不承担成本。本期 #N/A 成本单元格 {zero_count} 个。“-”沿用零费用标记；其他错误值将阻止生成。</p>
<p><b>BP：</b>{bp_note} 部分月的平台/品牌达成率使用“实际收入 × 月天数 ÷ 已过天数”；SKU 达成率使用实际收入，不外推；跨平台汇总只纳入有目标的平台 / 品牌 / SKU，确保分子分母范围一致。</p>
<p><b>库存：</b>读取 THD- robot Sell out 的 Inventory 列，按用户确认沿用。该列是本文件提供的库存快照，切换历史销售月份不会重建历史库存。</p>
<p><b>时间：</b>WoW 为 {cutoff-timedelta(days=13)}—{cutoff-timedelta(days=7)} 与 {cutoff-timedelta(days=6)}—{cutoff}。MoM 的 MTD 与整月比较已在表头注明；已完成季度比较最后两个完整月；当前季度不足整月时表头注明 MTD。Profit Waterfall 包括 Funding 扣减。</p>{revision}</div>
<div class="card"><h3>actual order 的重复行说明</h3>
<p>匹配键为日期、SKU、订单号、渠道、成本版本。同一键下内容完全相同的记录保留首条，避免重复计入销售与成本。费用旧副本排除后，本期范围内 {audit['raw_scope_rows']:,} 行，{audit['duplicate_groups']} 组业务字段重复（Filter 标记不参与业务去重），排除 {audit['removed_rows']} 条多余行，剩 {audit['retained_rows']:,} 行。排除的重复收入合计 ${audit['duplicate_revenue_removed']:,.2f}；其中本月排除 {current_duplicates} 条重复行。</p>
<p>本期费用冲突 {audit['conflicting_groups']} 组。下方行号可直接在原 Excel 的 actual order 中核对；原 Excel 未被删除或修改。以后若同一键下金额不同，更新会停止，等待确认。</p>
<details><summary>查看重复行明细</summary><div style="overflow-x:auto"><table><thead><tr><th>Excel 行号</th><th>日期</th><th>渠道</th><th>SKU</th><th>每条收入</th><th>排除条数</th></tr></thead><tbody>{dup_rows}</tbody></table></div></details></div>
<div class="card"><h3>检查与来源</h3><p>已核对各期间每日、渠道、品牌、动力源收入合计与总收入，以及 GM、各费用和 CM 的勾稽关系。THD 每日、每月销售合计一致。原始 Excel 与历史 W39 快照保留。</p>
<p>源表：actual order A:X；KPI Rawdata A:AJ；SKU MAP A:E；THD- robot Sell out A:G、I:J；2026 acutal cost 的对应月列。使用 Excel 已保存值；未重算源文件公式。页面仅在本地生成，尚未发布。</p><details><summary>文件核验信息</summary><p>SHA256：<code style="overflow-wrap:anywhere">{audit['source']['sha256']}</code></p></details></div></div>"""
    review=audit['margin_review'];wf=data['periods'][data['period_keys'][0]]['waterfalls']['Overall']
    bridge=[('Revenue',wf['gmv']),('COGS',wf['cogs']),('GM',wf['gm']),('Fixed cost',wf['fixed_cost']),('Marketing',wf['mkt_insite']+wf['mkt_offsite_seed']+wf['mkt_channel']),('Return + Warranty',wf['return_warranty']),('Funding',wf['funding']),('Warehouse + Shipping',0),('CM',wf['cm'])]
    bridge_rows=''.join(f'<tr><td class="name">{name}</td><td>${value:,.2f}</td><td>{value/wf["gmv"]*100:.2f}%</td></tr>' for name,value in bridge)
    differences=''.join(f'<tr><td class="name">{html.escape(v["channel"])} / {html.escape(v["brand"])}</td><td>{v["metric"]}</td><td>{v["cell"]}</td><td>${v["overview"]:,.2f}</td><td>${v["detail"]:,.2f}</td></tr>' for v in review['overview_differences'])
    zero_rows=''.join(f'<tr><td class="name">{html.escape(v["platform"])} / {v["brand"]}</td><td>{html.escape(v["sku"])}</td><td>${v["revenue"]:,.2f}</td></tr>' for v in review['zero_cogs_groups'])
    margin_notes=f"""<div class="card method-card"><div class="sec">GM → CM · {data['period_keys'][0]}</div>
<p><b>GM = Revenue − COGS；CM = GM − Fixed cost − Marketing − Return + Warranty − Funding。</b>百分比分母均为同范围、同期间 Revenue；各分项独立四舍五入，勾稽使用未舍入金额。CM 是本表已列费用后的贡献利润，不是公司净利润；未擅自补估未列费用。</p>
<p>Revenue 使用 actual order 的 V 列 Ordered Revenue；COGS 使用 D 列 Cost/ALL（已是整行成本，不再乘销量）；费用读取 F:K。平台汇总用金额加总后计算比率，不平均各渠道百分比。THD 汇总含 DS 和 DFC 订单；消费者 sell-out 另页展示，不重复并入收入。</p>
<div class="method-grid"><div><table><thead><tr><th>项目</th><th>USD</th><th>占收入</th></tr></thead><tbody>{bridge_rows}</tbody></table></div><div class="review-findings">
<h3>核对结果</h3><p>本月 {review['unit_cost_checks']:,} 条数字成本记录通过“单价 × 数量 = Cost/ALL”检查；{len(review['monthly_cost_checks'])} 项渠道 / 品牌收入及费用已与 2026 acutal cost 月度汇总核对；其中 {sum(v.get('reviewed_source_difference',False) for v in review['monthly_cost_checks'])} 项已复核的源表差异单独披露，其余在逐行分摊舍入范围内。Warehouse + Shipping 本月源表为 0，不另扣重复费用。</p>
<h3>零成本影响</h3><p>${review['zero_cogs_revenue']:,.2f} 收入对应源表零 COGS，占收入 {review['zero_cogs_revenue']/wf['gmv']*100:.1f}%。这些行在扣渠道费用前的 GM 等于收入，会抬高 GM。按已确认成本口径保留；未独立核实商品实际成本。</p>
<h3>汇总页与明细不一致</h3><p>over view 的部分已保存数值与订单明细不一致。采用与 2026 acutal cost 相互核对的订单明细；不混用汇总页的 GM / CM。具体原因无法仅凭数值导出确认，不能认定为已重算的财务汇总。</p></div></div>
<details><summary>查看汇总差异与零成本 SKU</summary><table><thead><tr><th>范围</th><th>指标</th><th>over view 单元格</th><th>汇总页</th><th>订单明细</th></tr></thead><tbody>{differences}</tbody></table><table><thead><tr><th>范围</th><th>零 COGS SKU</th><th>收入</th></tr></thead><tbody>{zero_rows}</tbody></table></details></div>"""
    review_note=''
    if audit.get('source_review'):
        source_review=audit['source_review']
        adjustment_rows=''.join(f"<tr><td>{html.escape(v['channel'])} / {html.escape(v['brand'])}</td><td>{v['source_cell']}</td><td>${v['source_total']:,.2f}</td><td>${v['allocated_detail']:,.2f}</td><td>${v['amount']:,.2f}</td></tr>" for v in source_review.get('monthly_cost_adjustments',[]))
        corrections='、'.join(f"{html.escape(cell)} → {html.escape(str(value))}" for cell,value in source_review.get('approved_cell_corrections',{}).items())
        source_differences='；'.join(f"{html.escape(cell)}：月度汇总 ${v['summary']:,.2f}，订单明细 ${v['detail']:,.2f}" for cell,v in source_review.get('known_monthly_source_differences',{}).items())
        review_note=f"<div class='card'><h3>本批次源表复核</h3><p>已按用户确认处理 actual order 的归月及空白费用：{corrections}；原始文件保留。通过与上期源表比对，{len(source_review.get('superseded_source_rows',[])):,} 条费用旧副本已排除。排除项与上期费用逐项一致，保留项为本次费用修订，并已与月度汇总交叉核对。Filter 标记不单独决定取舍；新增记录保留。</p><p>用户确认下列月度营销费用已经发生。仅扣入尚未分摊部分，不伪造订单或分配到 SKU。按渠道 / 品牌入账，动力源采用该范围源表一致的分类；订单数、销量、销售收入与商品成本不受费用补计影响。</p><table><thead><tr><th>范围</th><th>费用来源</th><th>月度费用</th><th>订单已分摊</th><th>独立补计</th></tr></thead><tbody>{adjustment_rows}</tbody></table><p>保留已复核的源表差异：{source_differences}。采用用户确认归月后的订单收入和已列费用，未将差异标为一致。</p></div>"
    notes=notes.replace('<div class="card"><h2',margin_notes+review_note+'<div class="card"><h2',1)
    preview=re.sub(r'^var DATA = .*;$',lambda _: 'var DATA = '+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+';',template,flags=re.M)
    preview=re.sub(r'<h1>.*?</h1>',f'<h1>STORM · {week} Weekly Business Cockpit</h1>',preview,count=1)
    preview=preview.replace('<head>',f'<head><title>STORM {week} · {cutoff.isoformat()}</title>',1)
    preview=re.sub(r'Through \d+/\d+',f'Through {cutoff.month}/{cutoff.day}',preview)
    preview=preview.replace('<button data-p="conclusions">Conclusions</button>','<button data-p="conclusions">Conclusions</button><button data-p="source-notes">数据口径</button>')
    preview=preview.replace('<div id="p-conclusions" class="panel"></div>','<div id="p-conclusions" class="panel"></div>'+notes)
    preview=preview.replace("{name:'CM (Net)',isSum:true,color:w.cm>=0?'#4CAF50':'#F44336'}", "{name:'Funding',y:-(w.funding||0),color:'#FF9800'},{name:'CM (Net)',isSum:true,color:w.cm>=0?'#4CAF50':'#F44336'}")
    preview=preview.replace("title:{text:'WoW Revenue (7-Day)'}", "title:{text:'WoW Revenue (7-Day)'},subtitle:{text:P.reproduction.w1+' vs '+P.reproduction.w2}")
    preview=preview.replace("dfcS.value=DATA.shared.dfc.available_months[0];", "dfcS.value=DATA.shared.dfc.available_months[DATA.shared.dfc.available_months.length-1];")
    preview=preview.replace('<th>Inventory</th>','<th>Inventory (source snapshot)</th>')
    preview=preview.replace("{l:'DFC AUG GMV',v:fmt$(DATA.shared.dfc.aug_gmv),s:DATA.shared.dfc.monthly_summary['2026-08'].units+' units',c:''}", "{l:'DFC '+DATA.shared.meta.dfc_label+' GMV',v:fmt$(DATA.shared.dfc.monthly_summary[DATA.shared.meta.dfc_period].gmv),s:DATA.shared.dfc.monthly_summary[DATA.shared.meta.dfc_period].units+' units',c:''}")
    preview=preview.replace('fmt$(ex.total_revenue*ex.gm_pct)','fmt$(P.waterfalls.Overall.gm)')
    preview=re.sub(r"(\bcurrentPeriod\s*=\s*)'Sep MTD'",lambda m:m.group(1)+repr(data['period_keys'][0]),preview)
    # No positive growth is fabricated when all SKUs declined (or vice versa).
    for element in ['wg-t','wd-t','mg-t','md-t']:
        pattern=r"(\$\('"+re.escape(element)+r"'\)\.innerHTML=.*?\.join\(''\))(;)"
        preview=re.sub(pattern,lambda m:m.group(1)+"||'<tr><td colspan=5 style=\"color:#64748b\">No SKUs in this direction.</td></tr>'"+m.group(2),preview)
    view=(Path(__file__).with_name('weekly_dashboard_view.html')).read_text(encoding='utf-8')
    css=re.search(r'<style>(.*?)</style>',view,re.S).group(1)
    js=re.search(r'<script>(.*?)</script>',view,re.S).group(1)
    preview=preview.replace('</style>',css+'\n</style>',1)
    preview=preview.replace('function renderAll(){',js+'\nfunction renderAll(){',1)
    start=preview.index('  // === Conclusions (dynamic per period) ===')
    end=preview.index('\n}\n\nvar wfC;',start)
    preview=preview[:start]+"  renderWeeklyReview(P);"+preview[end:]
    preview=preview.replace("(c.attainment>=1?'dot-g':c.attainment>=0.8?'dot-y':'dot-r')", "(c.bp<=0?'dot-n':c.attainment>=1?'dot-g':c.attainment>=0.8?'dot-y':'dot-r')")
    preview=preview.replace("+fmt$(c.bp)+", "+(c.bp>0?fmt$(c.bp):'未设目标')+")
    preview=preview.replace("(c.att_display?c.att_display+'%':'—')", "(c.bp>0?c.att_display+'%':'不适用')")
    preview=preview.replace("s:fmt$(P.waterfalls.Overall.gm),c:'green'", "s:fmt$(P.waterfalls.Overall.gm)+' · 扣商品成本后',c:''")
    preview=preview.replace("s:'Target: 5%'", "s:fmt$(P.waterfalls.Overall.cm)+' · 贡献利润'")
    preview=preview.replace('<div id="p-overview" class="panel on">','<div id="p-overview" class="panel on"><div id="margin-bridge" class="card"></div>')
    preview=preview.replace('<div id="p-bp" class="panel">','<div id="p-bp" class="panel"><p class="scope-note">Walmart / Sunseeker 未设 BP，不参与达成率评价。部分月平台达成率按日均外推；SKU 达成率按实际收入。</p>')
    preview=preview.replace('<div id="p-waterfall" class="panel">','<div id="p-waterfall" class="panel"><p class="scope-note">GM 仅扣商品成本；CM 再扣渠道费用、营销、退货 / 质保及 Funding，代表贡献利润。详见「数据口径」。</p>')
    preview=preview.replace("CM (Net)","CM (Contribution)")
    preview=preview.replace("text:'CM% = '+w.cm_pct_display+'%'", "text:w.gmv?'CM% = '+w.cm_pct_display+'%':'CM% 不适用（本期无收入）'")
    preview=preview.replace("return fmt$(Math.abs(this.y))+' ('+pct+'%)'", "return fmt$(Math.abs(this.y))+(w.gmv?' ('+pct+'%)':' · 比率不适用')")
    preview=preview.replace("+(i[1]/gmv*100).toFixed(1)+'%</td></tr>'", "+(w.gmv?(i[1]/gmv*100).toFixed(1)+'%':'不适用')+'</td></tr>'")
    (output/'index.html').write_text(preview,encoding='utf-8')

def validate_weekly(data):
    checks=[]
    for name,p in data['periods'].items():
        revenue=p['executive']['total_revenue'];wf=p['waterfalls']['Overall']
        for field in ['daily_trend','channel_overview','brand_performance','power_source','category_brand_heatmap']:
            delta=round(sum(v['revenue'] for v in p[field])-revenue,2)
            if abs(delta)>.02:raise ValueError(f'{name} {field} revenue mismatch {delta}')
            checks.append(f'{name}/{field}/revenue')
        if abs(round(wf['gmv']-sum(wf[k] for k in COSTS)-wf['cm'],2))>.02:
            raise ValueError(f'{name} CM reconciliation failed')
        checks.append(f'{name}/CM')
        for metric in ['gmv','gm','cm',*COSTS]:
            delta=round(sum(v[metric] for key,v in p['waterfalls'].items() if key!='Overall')-wf[metric],2)
            if abs(delta)>.02:raise ValueError(f'{name} platform/brand {metric} mismatch {delta}')
            checks.append(f'{name}/platform-brand/{metric}')
    dfc=data['shared']['dfc']
    for month,summary in dfc['monthly_summary'].items():
        for field in ['gmv','units','traffic']:
            if abs(sum(v[field] for v in dfc['daily_by_month'][month])-summary[field])>.02:
                raise ValueError(f'DFC {month} {field} mismatch')
            checks.append(f'DFC/{month}/{field}')
    return checks

def build_weekly(args):
    if not args.na_cost_zero_approved:
        raise ValueError('Weekly mode requires an explicitly confirmed #N/A zero-cost policy')
    source_hash=digest(args.source);baseline_hash=digest(args.baseline)
    review_policy=json.loads(args.source_review.read_text(encoding='utf-8')) if args.source_review else {}
    adjustments=review_policy.get('monthly_cost_adjustments',[])
    rows,raw_bp,dfc,inventory,audit=read_source(args.source,strict=True,na_cost_zero=True,review_policy=review_policy)
    bp=approved_weekly_bp(raw_bp)
    cutoff=max(r['date'] for r in rows)
    if set(range(1,cutoff.month+1))-{r['month'] for r in rows}:
        raise ValueError('Source is missing historical months required for YTD')
    definitions=weekly_definitions(cutoff)
    latest_dfc=max(r['date'] for r in dfc);dfc_period=latest_dfc.strftime('%Y-%m')
    label=calendar.month_abbr[latest_dfc.month].upper()+(' MTD' if latest_dfc.day<calendar.monthrange(latest_dfc.year,latest_dfc.month)[1] else '')
    data={'periods':{name:make_period(rows,bp,months,name,mom,cutoff,weekly=True,cost_adjustments=adjustments) for name,months,mom in definitions},
        'shared':{'colors':COLORS,'meta':{'data_through':cutoff.isoformat(),'dfc_data_through':latest_dfc.isoformat(),'pacing_factor':round(calendar.monthrange(cutoff.year,cutoff.month)[1]/cutoff.day,4),'dfc_period':dfc_period,'dfc_label':label},'dfc':make_dfc(dfc,inventory)},'period_keys':[d[0] for d in definitions]}
    for p in data['periods'].values():
        prepare_weekly_period(p,rows,cutoff,adjustments)
        apply_weekly_sku_bp_scope(p,rows,bp)
    audit['margin_review']=review_monthly_source(args.source,rows,cutoff,review_policy)
    audit['bp_excluded_raw_rows']=[v for v in raw_bp if (v['platform'],v['brand'])==('Walmart','Sunseeker')]

    audit.update({'source':{'file':args.source.name,'sha256':source_hash,'sheets':['actual order','KPI Rawdata','SKU MAP','THD- robot Sell out','2026 acutal cost']},'baseline':{'file':str(args.baseline),'sha256':baseline_hash},'data_through':cutoff.isoformat(),'dfc_data_through':latest_dfc.isoformat(),'zero_cost_policy':{'status':'USER_CONFIRMED','confirmed_on':'2026-09-29','rule':'#N/A costs = 0; included SKUs bear no cost; dash retains source zero representation'},'bp_policy':'USER_CONFIRMED 2026-09-29: Walmart / Sunseeker has no approved BP; exclude raw planning entries from targets and all attainment denominators; keep actual sales','duplicate_policy':'Only identical rows may be collapsed; conflicting same-key rows block weekly builds','duplicate_revenue_removed':round(sum(v['revenue']*v['extra_rows'] for v in audit['duplicates']),2),'validation':validate_weekly(data)})
    if args.previous_source:
        old_hash=digest(args.previous_source)
        old_rows,*_=read_source(args.previous_source)
        through=max(r['date'] for r in old_rows)
        old=[r for r in old_rows if r['month']==through.month and r['date']<=through]
        current=[r for r in rows if r['month']==through.month and r['date']<=through]
        audit['previous_source_comparison']={'file':args.previous_source.name,'sha256':old_hash,'through':through.isoformat(),'comparison_month':through.month,'old_revenue':total(old,'revenue'),'current_revenue':total(current,'revenue'),'revenue_revision':round(total(current,'revenue')-total(old,'revenue'),2),'old_cm':total(old,'cm'),'current_cm':total(current,'cm')}
        assert digest(args.previous_source)==old_hash
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'weekly_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output_dir/'source_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    write_weekly_preview(args.baseline.read_text(encoding='utf-8'),data,audit,args.output_dir)
    assert digest(args.source)==source_hash and digest(args.baseline)==baseline_hash
    print(json.dumps({'week':cutoff.isocalendar().week,'cutoff':str(cutoff),'executive':data['periods'][data['period_keys'][0]]['executive'],'validation_checks':len(audit['validation']),'duplicates_removed':audit['removed_rows'],'conflicting_groups':audit['conflicting_groups'],'output':str(args.output_dir)},ensure_ascii=False))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--mode',choices=['reproduce','weekly'],default='reproduce');ap.add_argument('--na-cost-zero-approved',action='store_true');ap.add_argument('--previous-source',type=Path);ap.add_argument('--source-review',type=Path);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--baseline',type=Path,default=Path('snapshots/storm_dashboard_cdn_2026-09-21_w39.html'));ap.add_argument('--output-dir',type=Path,required=True);args=ap.parse_args()
    safe_root=Path(__file__).resolve().parents[1]/'outputs'
    if not args.output_dir.resolve().is_relative_to(safe_root) or args.output_dir.resolve()==safe_root:
        raise ValueError('Private reproduction outputs must be in a subfolder of ignored outputs/')
    if args.mode=='weekly':
        build_weekly(args)
        return
    source_hash=digest(args.source);baseline_hash=digest(args.baseline)
    rows,bp,dfc,inventory,audit=read_source(args.source);cutoff=max(r['date'] for r in rows)
    if cutoff!=date(2026,9,21):raise ValueError('This historical reproduction is validated only for the W39 cutoff 2026-09-21')
    definitions=[('Sep MTD',[9],(8,9)),('Aug',[8],(7,8)),('Q3',[7,8,9],(7,8)),('Q2',[4,5,6],(5,6)),('Q1',[1,2,3],(2,3)),('YTD',list(range(1,10)),(8,9))]
    data={'periods':{label:make_period(rows,bp,months,label,mom,cutoff) for label,months,mom in definitions},'shared':{'colors':COLORS,'meta':{'data_through':cutoff.isoformat(),'pacing_factor':round(30/21,2)},'dfc':make_dfc(dfc,inventory)},'period_keys':[v[0] for v in definitions]}
    template=args.baseline.read_text(encoding='utf-8');baseline=json.loads(re.search(r'^var DATA = (.*);$',template,re.M).group(1))
    audit['source']={'file':args.source.name,'sha256':source_hash,'sheets':['actual order','KPI Rawdata','SKU MAP','THD- robot Sell out','2026 acutal cost']};audit['baseline']={'file':str(args.baseline),'sha256':baseline_hash};audit['comparison']=compare(baseline,data)
    audit['data_through']=cutoff.isoformat();audit['dfc_data_through']=max(r['date'] for r in dfc).isoformat()
    audit['cm_acceptance']='UNKNOWN'
    compatible_bp=[v for v in bp if not (v['platform']=='Walmart' and v['brand']=='Sunseeker')]
    audit['bp_exclusion_hypothesis']={'approval_status':'UNKNOWN','matches':0,'differences':[]}
    for label,months,mom in definitions:
        alternative=make_period(rows,compatible_bp,months,label,mom,cutoff)
        for field in ('platform_brand_bp','bp_att_lookup'):
            compare(baseline['periods'][label][field],alternative[field],label+'/'+field,audit['bp_exclusion_hypothesis'])
    for p in data['periods'].values():
        end=date.fromisoformat(p['daily_trend'][-1]['date'])
        p['reproduction']={'cm_status':'UNKNOWN','w1':f'{end-timedelta(days=13)} to {end-timedelta(days=7)}','w2':f'{end-timedelta(days=6)} to {end}'}
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'reconstructed_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output_dir/'reconciliation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    write_preview(template,data,baseline,audit,args.output_dir)
    assert source_hash==digest(args.source) and baseline_hash==digest(args.baseline)
    print(json.dumps({'cutoff':str(cutoff),'matches':audit['comparison']['matches'],'differences':len(audit['comparison']['differences']),'conflicting_groups':audit['conflicting_groups'],'output':str(args.output_dir)},ensure_ascii=False))

if __name__=='__main__':main()
