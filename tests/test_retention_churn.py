"""Regression checks for reviewed discovery-window churn; no network."""
import json
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
import url_lifecycle
import public_assets

ROOT = Path(url_lifecycle.__file__).parent
RULES = json.loads((ROOT / 'url.lifecycle').read_text())
NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
DATA_KEY = 'models' if RULES['detail_prefix']=='m' else 'items'

class RetentionChurnTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        entries = RULES['retained_references']
        rules = {k: RULES[k] for k in ('host', 'site_name', 'detail_prefix')}
        rules.update(captured_public_urls=['https://' + RULES['host'] + '/'] + [e['canonical_url'] for e in entries], retained_references=entries)
        (root / 'url.lifecycle').write_text(json.dumps(rules))
        (root / 'data.json').write_text(json.dumps({DATA_KEY: []}))
        (root / 'index.html').write_text('<!doctype html><title>Home</title>')
        (root / 'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://' + RULES['host'] + '/</loc></url></urlset>')
        (root / 'public.assets').write_text(json.dumps({'host': RULES['host'], 'root_files': ['index.html'], 'legacy_source_paths': []}))
        return root, rules, entries

    def test_all_reviewed_missing_records_keep_routes_schema_identity_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root, rules, entries = self.fixture(directory)
            self.assertEqual(url_lifecycle.render_retained(root), len(entries))
            self.assertEqual(url_lifecycle.verify(root)['explicitly_retired'], [])
            receipt = public_assets.seal(root)
            for e in entries:
                relative = e['canonical_url'].split('.com/', 1)[1] + 'index.html'
                body = (root / relative).read_text()
                self.assertIn('retained reference | ' + RULES['site_name'], body)
                self.assertIn('href="/">' + RULES['site_name'], body)
                self.assertIn('outside the current ranked discovery snapshot', body)
                self.assertIn('Catalog snapshot supporting this reference', body)
                self.assertIn(e['last_catalog_snapshot'], body)
                self.assertEqual(body.count('<h1>'), 1)
                self.assertIn('rel="canonical" href="' + e['canonical_url'] + '"', body)
                schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', body, re.S)[1])
                self.assertEqual(schema['@type'], 'CreativeWork' if DATA_KEY=='models' else 'SoftwareSourceCode')
                self.assertEqual(schema['url'], e['canonical_url'])
                self.assertEqual(schema['sameAs' if DATA_KEY=='models' else 'codeRepository'], e['repository'])
                self.assertNotIn('aggregateRating', schema)
                self.assertIn(relative, receipt['public_files'])
                self.assertIn(relative, public_assets.collect_public_files(root))
            self.assertNotIn('url.lifecycle', receipt['public_files'])
            self.assertNotIn('data.json', receipt['public_files'])
            target = root / (entries[0]['canonical_url'].split('.com/', 1)[1] + 'index.html')
            target.write_text(target.read_text() + '<!-- changed -->')
            with self.assertRaisesRegex(ValueError, 'stale'):
                public_assets.collect_public_files(root)

    def test_record_reentry_is_owned_by_ranked_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            root, rules, entries = self.fixture(directory)
            url_lifecycle.render_retained(root)
            e = entries[0]
            path = root / (e['canonical_url'].split('.com/', 1)[1] + 'index.html')
            path.write_text('fresh ranked generator output')
            (root / 'data.json').write_text(json.dumps({DATA_KEY: [{'slug': e['slug']}]}))
            url_lifecycle.render_retained(root)
            self.assertEqual(path.read_text(), 'fresh ranked generator output')

    def test_unreviewed_removal_stays_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root, rules, entries = self.fixture(directory)
            rules['captured_public_urls'].append('https://' + RULES['host'] + '/p/unreviewed-project/')
            (root / 'url.lifecycle').write_text(json.dumps(rules))
            url_lifecycle.render_retained(root)
            with self.assertRaisesRegex(ValueError, 'retention/retirement'):
                url_lifecycle.verify(root)

    def test_offhost_or_wrong_prefix_reference_rejected(self):
        for bad in ('https://other.invalid/p/project/', 'https://' + RULES['host'] + '/m/project/'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                root, rules, entries = self.fixture(directory)
                rules['retained_references'][0]['canonical_url'] = bad
                (root / 'url.lifecycle').write_text(json.dumps(rules))
                with self.assertRaisesRegex(ValueError, 'unsafe or mismatched'):
                    url_lifecycle.render_retained(root)
                # fixture uses the parsed module data, so restore for later cases.
                RULES['retained_references'] = json.loads((ROOT / 'url.lifecycle').read_text())['retained_references']

    def test_retained_output_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, rules, entries = self.fixture(directory)
            path = root / (entries[0]['canonical_url'].split('.com/', 1)[1] + 'index.html')
            path.parent.mkdir(parents=True)
            outside = root / 'outside.html'
            outside.write_text('preserve')
            path.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                url_lifecycle.render_retained(root)
            self.assertEqual(outside.read_text(), 'preserve')



class November7PublishedRouteTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory).resolve()
        rules = json.loads((ROOT / 'url.lifecycle').read_text())
        entries = json.loads((ROOT / 'tests/fixtures/gateway-retention-20261107.json').read_text())
        missing = {e['canonical_url'] for e in entries}
        protected = set(rules['captured_public_urls']) | set(rules.get('planned_release_urls', []))
        (root / 'url.lifecycle').write_text(json.dumps(rules))
        (root / 'data.json').write_text('{"items":[]}')
        (root / 'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+u+'</loc></url>' for u in protected-missing)+'</urlset>')
        return root, rules, entries
    def test_three_actual_rotated_routes_are_restored_with_dated_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root, rules, entries = self.fixture(d)
            with self.assertRaisesRegex(ValueError,'retention/retirement'): url_lifecycle.verify(root)
            url_lifecycle.render_retained(root)
            self.assertTrue({e['canonical_url'] for e in entries}.issubset(url_lifecycle.urls(root)), 'Reviewed protected URLs must survive discovery rotation')
            self.assertEqual(url_lifecycle.verify(root)['explicitly_retired'],[])
            for e in entries:
                self.assertIn(e['canonical_url'],url_lifecycle.urls(root))
                body=(root/e['canonical_url'].split('.com/',1)[1]/'index.html').read_text()
                self.assertIn('2026-11-06T18:02:54.817637+00:00',body)
                self.assertIn(e['primary_sources'][0]['url'],body)
                self.assertIn('Retained reference — outside the current ranked discovery snapshot.',body)
                schema=json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',body,re.S)[1])
                self.assertEqual(schema['url'],e['canonical_url']);self.assertNotIn('aggregateRating',schema)
    def test_new_reference_reentry_keeps_current_generator_pages(self):
        with tempfile.TemporaryDirectory() as d:
            root,rules,entries=self.fixture(d)
            (root/'data.json').write_text(json.dumps({'items':[{'slug':e['slug']} for e in entries]}))
            for e in entries:
                path=root/e['canonical_url'].split('.com/',1)[1]/'index.html';path.parent.mkdir(parents=True);path.write_text('fresh current page')
            url_lifecycle.render_retained(root)
            for e in entries:self.assertEqual((root/e['canonical_url'].split('.com/',1)[1]/'index.html').read_text(),'fresh current page')
    def test_unknown_fourth_removal_remains_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root,rules,entries=self.fixture(d);rules['captured_public_urls'].append('https://gateway.kymatalabs.com/p/unreviewed-fourth/')
            (root/'url.lifecycle').write_text(json.dumps(rules));url_lifecycle.render_retained(root)
            with self.assertRaisesRegex(ValueError,'retention/retirement'):url_lifecycle.verify(root)

if __name__ == '__main__':
    unittest.main()
