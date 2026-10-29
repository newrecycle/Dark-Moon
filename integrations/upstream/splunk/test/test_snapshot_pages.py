import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('paged_forwarder',ROOT/'forwarder/darkmoon-to-hec.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def page(rows,offset,total,more,next_offset):
    return {'data':rows,'offset':offset,'limit':1,'total':total,'has_more':more,'next_offset':next_offset}

class SnapshotPages(unittest.TestCase):
    def read(self,pages,**kwargs):
        with patch.object(f,'_get_json',side_effect=pages) as get:
            rows=f.read_collection('https://owned.invalid/api/v1/vulnerabilities',{'Authorization':'Bearer fixture'},True,**kwargs)
            return rows,get.call_args_list
    def test_complete_pages_use_only_local_constructed_offsets_and_scoped_finding_keys(self):
        a={'id':'same','campaign_id':'camp_a'};b={'id':'same','campaign_id':'camp_b'}
        rows,calls=self.read([page([a],0,2,True,1),page([b],1,2,False,None)],findings=True)
        self.assertEqual(rows,[a,b]);self.assertTrue(calls[1].args[0].endswith('?offset=1&limit=1'))
    def test_no_partial_snapshot_on_overlap_gap_changing_count_or_bad_cursor(self):
        a={'id':'one'};b={'id':'two'}
        for second in [page([a],1,2,False,None),page([b],3,2,False,None),page([b],1,3,False,None),page([b],1,2,False,2)]:
            with self.subTest(second=second),self.assertRaises(ValueError):
                self.read([page([a],0,2,True,1),second])
    def test_unpaged_truncation_and_partial_paging_are_errors(self):
        for value in [{'data':[],'total':1},{'data':[],'has_more':True},page([],0,1,True,0),page([{'id':'x'}],0,2,True,'https://external.invalid')]:
            with self.subTest(value=value),self.assertRaises(ValueError):self.read([value])
        self.assertEqual(self.read([{'data':[],'total':0}])[0],[])
    def test_latest_macros_filter_after_latest_selection(self):
        import configparser
        c=configparser.ConfigParser(interpolation=None);c.read(ROOT/'darkmoon/default/macros.conf')
        for name in ('darkmoon_open_findings','darkmoon_findings_by_severity(1)'):
            self.assertTrue(c[name]['definition'].startswith('`darkmoon_latest_findings` | search'))
if __name__=='__main__':unittest.main()
