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

if __name__=='__main__':unittest.main()
