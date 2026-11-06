import unittest,json,pathlib
from unittest.mock import patch
import build_data
class EditorialCurationTests(unittest.TestCase):
 def test_reviewed_promotional_examples_do_not_enter_ranked_catalog(self):
  for name in json.loads(pathlib.Path('editorial_reviews.json').read_text()):
   if name.startswith('apimart'):
    self.assertFalse(build_data.is_gateway({'full_name':name,'name':'gateway','description':'AI gateway','topics':['ai-gateway']}),name)
 def test_unreviewed_repository_is_not_excluded_by_similar_name(self):
  self.assertTrue(build_data.is_gateway({'full_name':'apimart-example/actual-gateway','topics':['ai-gateway']}))
 def test_documented_architectures_are_preserved_in_data(self):
  records=[{'full_name':n,'name':n.split('/')[1],'description':'The Cloud-Native API Gateway and AI Gateway','stargazers_count':200,'html_url':'https://github.com/'+n} for n in ['apache/apisix','kgateway-dev/kgateway']]
  with patch.object(build_data,'QUERIES',['test']),patch.object(build_data,'search',return_value=records),patch.object(build_data.time,'sleep'):
   rows=build_data.build_items()
  self.assertNotEqual(rows[0]['description'],rows[1]['description'])
  for x in rows:
   self.assertEqual(x['source_description'],'The Cloud-Native API Gateway and AI Gateway')
   self.assertEqual(x['description_review']['reviewed_on'],'2026-11-06')
 def test_curated_references_preserve_historic_routes(self):
  reviews=json.loads(pathlib.Path('editorial_reviews.json').read_text());policy=json.loads(pathlib.Path('url.lifecycle').read_text());retained={x['entity'].lower():x for x in policy['retained_references']}
  for name,review in reviews.items():
   if review['decision']=='reference_only':
    self.assertIn(name,retained);self.assertIn(review['documented_model'],retained[name]['summary']);self.assertTrue(retained[name]['evidence_sha256'])
if __name__=='__main__':unittest.main()
