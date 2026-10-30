"""Focused synthetic tests for historical reconstruction (no business fixtures)."""
import importlib.util
from pathlib import Path
import unittest
from datetime import date
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('reproduction',Path(__file__).parents[1]/'scripts'/'reproduce_weekly_dashboard.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def row(day, revenue, order='ORDER-1', sku='TEST-SKU'):
    costs=dict.fromkeys(r.COSTS,0.0);costs['cogs']=revenue*.4;costs['funding']=revenue*.1
    return {'date':date(2026,9,day),'month':9,'sku':sku,'platform':'Walmart','channel':'Walmart / MP','brand':'Sunseeker','power':'Robot','category':'Robot Mower','order':order,'revenue':revenue,'units':1,'cm':revenue*.5,**costs}

class ReconstructionTests(unittest.TestCase):
    def test_mixed_date_formats(self):
        self.assertEqual(r.parse_date('09/07/2026'),date(2026,9,7))
        self.assertEqual(r.parse_date('2026-09-07 00:00:00'),date(2026,9,7))
        self.assertEqual(r.parse_date(46272),date(2026,9,7))
        with self.assertRaises(ValueError):r.parse_date('not-a-date')

    def test_equal_week_windows_exclude_day_before_window(self):
        rows=[row(7,999),row(8,20),row(14,30),row(15,40),row(21,60)]
        p=r.make_period(rows,[],[9],'Sep MTD',(8,9),date(2026,9,21))
        self.assertEqual((p['executive']['w1'],p['executive']['w2']),(50,100))
        self.assertEqual(p['executive']['wow_display'],100)

    def test_bp_includes_walmart_sunseeker_and_sku_is_not_paced(self):
        rows=[row(21,70)]
        bp=[{'month':9,'platform':'Walmart','brand':'Sunseeker','sku':'TEST-SKU','revenue':100}]
        p=r.make_period(rows,bp,[9],'Sep MTD',(8,9),date(2026,9,21))
        self.assertEqual(p['platform_brand_bp'][0]['projected'],100)
        self.assertEqual(p['platform_brand_bp'][0]['bp'],100)
        self.assertEqual(p['bp_att_lookup']['by_sku_all']['TEST-SKU'],70)

    def test_weekly_no_target_preserves_sales_and_excludes_unapproved_bp(self):
        rows=[row(28,70)]
        raw=[{'month':9,'platform':'Walmart','brand':'Sunseeker','sku':'TEST-SKU','revenue':100}]
        bp=r.approved_weekly_bp(raw)
        p=r.make_period(rows,bp,[9],'Sep MTD',(8,9),date(2026,9,28))
        r.prepare_weekly_period(p,rows,date(2026,9,28))
        self.assertEqual(raw[0]['revenue'],100)
        self.assertEqual(p['executive']['total_revenue'],70)
        self.assertEqual(p['platform_brand_bp'][0]['target_status'],'NOT_SET')
        self.assertIsNone(p['platform_brand_bp'][0]['att_display'])
        self.assertEqual(p['bp_att_lookup']['by_sku_all'],{})
        self.assertEqual([b['brand'] for b in p['conclusions']['Walmart']['brands']],['Badger','Sunseeker'])

    def test_sku_bp_aggregate_uses_matching_scope(self):
        unplanned=row(28,70)
        planned=dict(row(28,30),platform='THD',channel='THD / DS')
        bp=[{'month':9,'platform':'THD','brand':'Sunseeker','sku':'TEST-SKU','revenue':100}]
        p=r.make_period([unplanned,planned],bp,[9],'Sep MTD',(8,9),date(2026,9,28))
        r.apply_weekly_sku_bp_scope(p,[unplanned,planned],bp)
        self.assertEqual(p['bp_att_lookup']['by_sku_all']['TEST-SKU'],30)
        self.assertEqual(p['bp_att_lookup']['by_platform']['Walmart'],{})

    def test_funding_is_in_cm(self):
        w=r.waterfall([row(21,100)])
        self.assertEqual(w['gm'],60);self.assertEqual(w['funding'],10);self.assertEqual(w['cm'],50)

    def test_dfc_weighted_conversion_and_zero_inventory_preserved(self):
        rows=[{'date':date(2026,9,1),'month':'2026-09','sku':'A','gmv':10,'units':1,'traffic':10},{'date':date(2026,9,2),'month':'2026-09','sku':'A','gmv':30,'units':3,'traffic':90}]
        d=r.make_dfc(rows,{'A':0})
        self.assertEqual(d['monthly_summary']['2026-09']['conv_rate'],.04)
        self.assertEqual(d['inventory']['A'],0)
        self.assertNotIn('B',d['inventory'])

    def test_ranking_ties_are_deterministic(self):
        a=[row(1,10,sku='B'),row(1,10,sku='A')];b=[row(2,10,sku='B'),row(2,10,sku='A')]
        self.assertEqual([v['sku'] for v in r.sku_changes(a,b,('w1','w2'),5)['growth']],['A','B'])

    def test_comparison_preserves_missing_versus_zero(self):
        c=r.compare({'x':0},{})
        self.assertEqual(len(c['differences']),1)

    def test_duplicate_conflict_and_invalid_cost_are_exposed(self):
        headers=['Filter','Cost - Type','Cost/UNIT','Cost/ALL','ASP','Fixed cost','MKT-Insite','MKT-Offsite','Return+Warranty','Funding','MKT-Channel','Month-EN','PowerSource','Brand','DI','Year','Month','Date','Country','Channel','SKU','Ordered Revenue','Ordered Units','Order Number']
        a=[0,'V1',10,'#N/A',100,2,3,'-',4,'-','-','Sep','Robot','Sunseeker','N',2026,9,'09/21/2026','US','Walmart Seller','TEST-SKU',100,1,'ORDER-1']
        b=list(a);b[6]=13
        class Sheet:
            def __init__(self,values):self.values=values
            def iter_rows(self,min_row=1,values_only=True):return iter(self.values[min_row-1:])
        class Book(dict):
            def close(self):pass
        book=Book({'actual order':Sheet([headers,a,b]),'SKU MAP':Sheet([['SKU','ASIN','Power','Brand','Category'],['TEST-SKU','ID','Robot','Sunseeker','Robot Mower']]),'KPI Rawdata':Sheet([['header']]),'THD- robot Sell out':Sheet([['header']])})
        with patch.object(r.openpyxl,'load_workbook',return_value=book):
            rows,_,_,_,audit=r.read_source(Path('synthetic.xlsx'))
        self.assertEqual(audit['removed_rows'],1)
        self.assertEqual(audit['conflicting_groups'],1)
        self.assertTrue(any(v['value']=='#N/A' and v['cell']=='D2' for v in audit['nonnumeric_costs']))
        self.assertEqual(audit['cost_sensitivity'][-1]['delta_last_minus_first'],-10)
        self.assertEqual(rows[0]['mkt_insite'],3)
        with patch.object(r.openpyxl,'load_workbook',return_value=book):
            with self.assertRaisesRegex(ValueError,'Unapproved cost value'):
                r.read_source(Path('synthetic.xlsx'),strict=True,na_cost_zero=False)
        with patch.object(r.openpyxl,'load_workbook',return_value=book):
            with self.assertRaisesRegex(ValueError,'conflicting values'):
                r.read_source(Path('synthetic.xlsx'),strict=True,na_cost_zero=True)
        book['actual order']=Sheet([headers,a])
        with patch.object(r.openpyxl,'load_workbook',return_value=book):
            approved,*_=r.read_source(Path('synthetic.xlsx'),strict=True,na_cost_zero=True)
        self.assertEqual(approved[0]['cogs'],0)
        a[3]='#REF!'
        with patch.object(r.openpyxl,'load_workbook',return_value=book):
            with self.assertRaisesRegex(ValueError,'Unapproved cost value'):
                r.read_source(Path('synthetic.xlsx'),strict=True,na_cost_zero=True)

    def test_weekly_cm_display_does_not_round_twice(self):
        sample=row(28,100);sample['cm']=8.448;sample['cogs']=91.552;sample['funding']=0
        p=r.make_period([sample],[],[9],'Sep MTD',(8,9),date(2026,9,28))
        r.prepare_weekly_period(p,[sample],date(2026,9,28))
        self.assertEqual(p['executive']['cm_display'],8.4)
        self.assertEqual(p['executive']['cm_display'],p['waterfalls']['Overall']['cm_pct_display'])

    def test_weekly_filters_do_not_label_declines_as_growth(self):
        rows=[row(21,100),row(28,20)]
        p=r.make_period(rows,[],[9],'Sep MTD',(8,9),date(2026,9,28))
        r.prepare_weekly_period(p,rows,date(2026,9,28))
        self.assertEqual(p['sku_wow_growth'],[])
        self.assertEqual(p['platform_sku_wow']['Walmart']['growth'],[])
        self.assertEqual(p['sku_wow_decline'][0]['change'],-80)

    def test_weekly_periods_keep_historical_quarters(self):
        definitions=r.weekly_definitions(date(2026,9,28))
        self.assertEqual([v[0] for v in definitions],['Sep MTD','Aug','Q3','Q2','Q1','YTD'])
        self.assertEqual(definitions[2][2],(7,8))
        with self.assertRaisesRegex(ValueError,'rollover'):
            r.weekly_definitions(date(2027,1,20))

    def test_october_weekly_windows_include_previous_month(self):
        previous=dict(row(30,80),date=date(2026,9,30))
        current=dict(row(7,20),date=date(2026,10,7),month=10)
        p=r.make_period([previous,current],[],[10],'Oct MTD',(9,10),date(2026,10,7),weekly=True)
        r.prepare_weekly_period(p,[previous,current],date(2026,10,7))
        self.assertEqual(p['executive']['total_revenue'],20)
        self.assertEqual((p['executive']['w1'],p['executive']['w2']),(80,20))
        self.assertEqual(p['executive']['wow_display'],-75)
        sun=p['conclusions']['Walmart']['brands'][1]
        self.assertEqual((sun['w1'],sun['w2'],sun['wow']),(80,20,-75))

    def test_monthly_expense_without_orders_is_not_fabricated_as_an_order(self):
        current=dict(row(7,100),date=date(2026,10,7),month=10)
        adjustment={'month':10,'platform':"Lowe's",'channel':"Lowe's / DS",'brand':'Sunseeker','power':'Robot','metric':'mkt_insite','amount':15}
        p=r.make_period([current],[],[10],'Oct MTD',(9,10),date(2026,10,7),weekly=True,cost_adjustments=[adjustment])
        r.prepare_weekly_period(p,[current],date(2026,10,7),[adjustment])
        self.assertEqual((p['executive']['total_revenue'],p['executive']['total_orders'],p['executive']['total_units']),(100,1,1))
        self.assertEqual(p['waterfalls']['Overall']['cm'],35)
        self.assertEqual(p['waterfalls']["Lowe's / Sunseeker"]['cm'],-15)
        self.assertIsNone(p['waterfalls']["Lowe's / Sunseeker"]['cm_pct_display'])
        self.assertEqual(p['brand_performance'][0]['cm_display'],35)
        self.assertEqual(p['power_source'][0]['cm_display'],35)
        self.assertTrue(p['conclusions']["Lowe's"]['brands'][1]['has_data'])
        self.assertEqual(p['conclusions']["Lowe's"]['cm'],-15)
        self.assertEqual(r.waterfall([current])['cm'],50)
        prior=r.make_period([row(30,100)],[],[9],'Sep',(8,9),date(2026,10,7),cost_adjustments=[adjustment])
        self.assertEqual(prior['waterfalls']['Overall']['cm'],50)

    def test_october_period_definitions(self):
        definitions=r.weekly_definitions(date(2026,10,7))
        self.assertEqual([v[0] for v in definitions],['Oct MTD','Sep','Q4','Q3','Q2','Q1','YTD'])
        self.assertEqual(definitions[2][1],[10])
        self.assertEqual(definitions[3][1],[7,8,9])
        self.assertEqual(definitions[3][2],(8,9))

    def test_q4_never_drops_q1(self):
        for month in (10,11,12):
            with self.subTest(month=month):
                definitions=r.weekly_definitions(date(2026,month,7))
                quarters=[v for v in definitions if v[0].startswith('Q')]
                self.assertEqual([v[0] for v in quarters],['Q4','Q3','Q2','Q1'])
                self.assertEqual(quarters[-1],('Q1',[1,2,3],(2,3)))
                self.assertEqual(definitions[-1][0],'YTD')

    def test_previous_snapshot_uses_its_reviewed_monthly_expenses(self):
        old=dict(row(7,100),date=date(2026,10,7),month=10)
        current=dict(row(7,120),date=date(2026,10,7),month=10)
        later=dict(row(12,999),date=date(2026,10,12),month=10)
        base={'month':10,'platform':"Lowe's",'channel':"Lowe's / DS",'brand':'Sunseeker','power':'Robot','metric':'mkt_insite'}
        policy={'monthly_cost_adjustments':[dict(base,amount=15)]}
        with patch.object(r,'read_source',return_value=([old],[],[],{},{})) as reader, patch.object(r,'digest',return_value='HASH'):
            comparison=r.compare_previous_source(Path('previous.xlsx'),[current,later],[dict(base,amount=20)],policy)
        self.assertEqual((comparison['old_revenue'],comparison['current_revenue']),(100,120))
        self.assertEqual((comparison['old_cm'],comparison['current_cm']),(35,40))
        self.assertTrue(comparison['previous_source_review_applied'])
        self.assertEqual(reader.call_args.kwargs['review_policy'],policy)

class MonthlySourceTests(unittest.TestCase):
    labels=[('GMV','revenue'),('Fixed Cost','fixed_cost'),('MKT-Insite','mkt_insite'),('MKT-Offsite(种草)','mkt_offsite_seed'),('MKT-Offsite(Channel MKT)','mkt_channel'),('Return+Warranty','return_warranty'),('Funding','funding'),('Warehouse+Shipping','warehouse_shipping')]

    def fixture(self,samples=None):
        samples=samples or [row(21,100)]
        actual=[['header']*24];records=[]
        for n,sample in enumerate(samples,2):
            sample=dict(sample,source_row=n);records.append(sample)
            raw=[None]*24;raw[2]=sample['cogs']/sample['units'];raw[3]=sample['cogs']
            for metric,col in r.COSTS.items():raw[col]=sample[metric]
            for col,value in {13:sample['brand'],15:2026,16:sample['month'],17:sample['date'],18:'US',19:'Walmart Seller',20:sample['sku'],21:sample['revenue'],22:sample['units'],23:sample['order']}.items():raw[col]=value
            actual.append(raw)
        monthly=[]
        for label,metric in self.labels:
            values=[label,'Walmart Seller','Sunseeker',None,None]+[0]*12
            for month in range(1,11):values[month+4]=sum(x.get(metric,0) for x in records if x['month']==month)
            monthly.append(values)
        return actual,monthly,records

    def adjustment(self,metric,month,amount):
        n=next(n for n,(_,key) in enumerate(self.labels,1) if key==metric)
        return {'month':month,'platform':'Walmart','channel':'Walmart / MP','brand':'Sunseeker','power':'Robot','metric':metric,'source_sheet':'2026 acutal cost','source_cell':f'{r.openpyxl.utils.get_column_letter(month+5)}{n}','source_total':amount,'allocated_detail':0,'amount':amount}

    def test_historical_no_sales_fee_blocks_without_an_approved_adjustment(self):
        actual,monthly,records=self.fixture();monthly[2][5]=25
        with self.assertRaisesRegex(ValueError,'month 1'):
            r.reconcile_monthly_costs(actual,monthly,records,date(2026,9,21),{})
        adjustment=self.adjustment('mkt_insite',1,25)
        checks,warehouse=r.reconcile_monthly_costs(actual,monthly,records,date(2026,9,21),{'monthly_cost_adjustments':[adjustment]})
        self.assertEqual({x['month'] for x in checks},set(range(1,10)))
        self.assertEqual((len(checks),len(warehouse)),(63,9))
        check=next(x for x in checks if x['cell']=='F3')
        self.assertEqual((check['detail'],check['independent_cost'],check['reconciliation_delta']),(25,25,0))

    def test_deduplicated_fees_are_an_explicit_bridge(self):
        actual,monthly,records=self.fixture([row(21,100),row(21,100)])
        checks,_=r.reconcile_monthly_costs(actual,monthly,records[:1],date(2026,9,21),{})
        check=next(x for x in checks if x['month']==9 and x['metric']=='funding')
        self.assertEqual((check['summary'],check['detail'],check['removed_duplicate'],check['reconciliation_delta']),(20,10,10,0))
        monthly[6][13]+=5
        with self.assertRaisesRegex(ValueError,'unexplained -5'):
            r.reconcile_monthly_costs(actual,monthly,records[:1],date(2026,9,21),{})

    def test_old_seed_marketing_and_warehouse_shipping_are_checked(self):
        actual,monthly,records=self.fixture();monthly[3][5]=25
        with self.assertRaisesRegex(ValueError,'month 1'):
            r.reconcile_monthly_costs(actual,monthly,records,date(2026,9,21),{})
        monthly[3][5]=0;monthly[7][5]=5
        with self.assertRaisesRegex(ValueError,'Warehouse'):
            r.reconcile_monthly_costs(actual,monthly,records,date(2026,9,21),{})

    def test_blank_or_missing_historical_summary_blocks(self):
        actual,monthly,records=self.fixture();monthly[2][5]=None
        with self.assertRaisesRegex(ValueError,'Missing monthly'):
            r.reconcile_monthly_costs(actual,monthly,records,date(2026,9,21),{})
        with self.assertRaisesRegex(ValueError,'coverage'):
            r.reconcile_monthly_costs(actual,monthly[:2]+monthly[3:],records,date(2026,9,21),{})

    def test_duplicate_stale_or_wrong_scope_adjustments_block(self):
        actual,monthly,records=self.fixture();monthly[2][5]=25
        approved=self.adjustment('mkt_insite',1,25)
        for values in [[approved,approved],[dict(approved,amount=24)],[dict(approved,source_total=24)],[dict(approved,allocated_detail=1)],[dict(approved,month=2)],[dict(approved,source_cell='NOT-A-CELL')]]:
            with self.subTest(values=values),self.assertRaisesRegex(ValueError,'adjustment'):
                r.reconcile_monthly_costs(actual,monthly,records,date(2026,9,21),{'monthly_cost_adjustments':values})

    def test_reviewed_export_difference_is_exact_and_requires_a_reason(self):
        actual,monthly,records=self.fixture();monthly[0][13]=102
        exception={'summary':102,'detail':100,'removed_duplicate':0,'reason':'Reviewed export precision difference'}
        checks,_=r.reconcile_monthly_costs(actual,monthly,records,date(2026,9,21),{'known_monthly_source_differences':{'N1':exception}})
        check=next(x for x in checks if x['cell']=='N1')
        self.assertFalse(check['within_rounding']);self.assertTrue(check['reviewed_source_difference'])
        for change in [dict(exception,detail=99),dict(exception,reason='')]:
            with self.assertRaisesRegex(ValueError,'summary differs'):
                r.reconcile_monthly_costs(actual,monthly,records,date(2026,9,21),{'known_monthly_source_differences':{'N1':change}})

    def test_historical_adjustment_propagates_only_to_its_month_and_rollups(self):
        jan=dict(row(21,100,order='JAN'),month=1,date=date(2026,1,21))
        oct=dict(row(12,100,order='OCT'),month=10,date=date(2026,10,12))
        adjustment=self.adjustment('mkt_insite',1,15)
        for months,expected in [([1],35),([1,2,3],35),(list(range(1,11)),85),([10],50),([7,8,9],None)]:
            if expected is None:continue
            p=r.make_period([jan,oct],[],months,'test',(9,10),date(2026,10,12),weekly=True,cost_adjustments=[adjustment])
            self.assertEqual(p['waterfalls']['Overall']['cm'],expected)
            self.assertEqual(p['executive']['total_orders'],2 if len(months)==10 else 1)

    def test_historical_unit_cost_rounding_is_quantity_bounded(self):
        sample=dict(row(21,2000),month=1,date=date(2026,1,21),units=20,cogs=800.08)
        actual,monthly,records=self.fixture([sample]);actual[1][2]=40
        class Sheet:
            def __init__(self,values):self.values=values
        class Book(dict):
            def close(self):pass
        book=Book({'actual order':Sheet(actual),'2026 acutal cost':Sheet(monthly),'over view':Sheet([[None,None],[None,'Unknown'],[None,None]])})
        with patch.object(r.openpyxl,'load_workbook',return_value=book):
            result=r.review_monthly_source(Path('synthetic.xlsx'),records,date(2026,9,21),{})
        self.assertEqual((result['unit_cost_checks'],result['unit_cost_mismatches']),(1,[]))
        actual[1][3]=800.2
        with patch.object(r.openpyxl,'load_workbook',return_value=book),self.assertRaisesRegex(ValueError,'Unit cost'):
            r.review_monthly_source(Path('synthetic.xlsx'),records,date(2026,9,21),{})

    def test_private_outputs_cannot_overwrite_public_project_paths(self):
        project=Path(__file__).resolve().parents[1]
        for path in [project,project/'dashboard',project/'snapshots',project/'outputs',Path(project.anchor)]:
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'Private outputs'):
                r.private_output_directory(path)
        legacy=project/'outputs'/'synthetic';outside=project.parent/'private-synthetic'
        self.assertEqual(r.private_output_directory(legacy),legacy.resolve())
        self.assertEqual(r.private_output_directory(outside),outside.resolve())

if __name__=='__main__':unittest.main()
