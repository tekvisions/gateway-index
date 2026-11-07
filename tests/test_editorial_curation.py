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
class DescriptionPopulationTests(unittest.TestCase):
 def test_repeated_commercial_copy_requires_review_without_mutating_rows(self):
  text = 'AI gateway / relay with one compatible key. USD settlement and commercial pricing from $0.01 per request.'
  rows = [{'full_name':f'publisher-{i}/gateway','description':text} for i in range(3)]
  with self.assertRaisesRegex(ValueError, 'requires source review'):
   build_data.verify_description_population(rows)
  self.assertEqual(len(rows),3)
 def test_distinct_source_descriptions_and_short_generic_labels_are_allowed(self):
  build_data.verify_description_population([{'full_name':f'p{i}/gateway','description':'API Gateway'} for i in range(5)])
  build_data.verify_description_population([{'full_name':f'p{i}/gateway','description':f'Provider {i} implementation, documented API routing and independently described capabilities; price $1.'} for i in range(3)])


class UnpublishedPromotionalCandidateTests(unittest.TestCase):
 def candidates(self):
  return json.loads(pathlib.Path('tests/fixtures/unpublished-router-candidates-20261107.json').read_text())
 def test_reviewed_model_documentation_is_excluded_before_population_check(self):
  with patch.object(build_data,'QUERIES',['fixture']),patch.object(build_data,'search',return_value=self.candidates()),patch.object(build_data.time,'sleep'):
   rows=build_data.build_items()
  self.assertEqual(rows,[])
  build_data.verify_description_population(rows)
 def test_unknown_repeated_commercial_candidates_still_block(self):
  records=self.candidates()
  for i,r in enumerate(records): r['full_name']=f'unknown-{i}/gateway'
  with patch.object(build_data,'QUERIES',['fixture']),patch.object(build_data,'search',return_value=records),patch.object(build_data.time,'sleep'):
   rows=build_data.build_items()
  with self.assertRaisesRegex(ValueError,'requires source review'): build_data.verify_description_population(rows)
  self.assertEqual(len(rows),3)
 def test_same_publisher_real_gateway_is_not_blanket_excluded(self):
  self.assertTrue(build_data.is_gateway({'full_name':'apimartn0e1fufu/independent-gateway','topics':['ai-gateway']}))
 def test_previously_published_retained_sdk_node_survives(self):
  import tempfile,url_lifecycle
  from pathlib import Path
  policy=json.loads(pathlib.Path('url.lifecycle').read_text());canonical='https://gateway.kymatalabs.com/p/apimartn0e1fufu-api-router-sdk-node/'
  with tempfile.TemporaryDirectory() as d:
   root=Path(d).resolve();(root/'url.lifecycle').write_text(json.dumps(policy));(root/'data.json').write_text('{"items":[]}')
   protected=set(policy['captured_public_urls'])|set(policy.get('planned_release_urls',[]))
   (root/'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+u+'</loc></url>' for u in protected-{canonical})+'</urlset>')
   url_lifecycle.render_retained(root);self.assertIn(canonical,url_lifecycle.urls(root));self.assertEqual(url_lifecycle.verify(root)['explicitly_retired'],[])
   self.assertTrue((root/'p/apimartn0e1fufu-api-router-sdk-node/index.html').exists())

if __name__=='__main__':unittest.main()
