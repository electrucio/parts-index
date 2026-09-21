-- A corpus small enough to read, exercising every branch the export has to get right.
--
-- SQL text rather than a .sqlite file: the guard refuses binary databases, and a fixture nobody can read
-- in a diff is a fixture nobody will correct. `tests/schematics/test_export.py` builds a database from
-- this and exports it.
--
-- Eight documents. Three earn their link three different ways, three are refused for three different
-- reasons, one is a figure hanging off a page, and one is withdrawn.

CREATE TABLE documents (
  doc_id INTEGER PRIMARY KEY, source TEXT, doc_key TEXT, role TEXT, parent_doc_id INTEGER,
  title TEXT, public_url TEXT, page_url_tpl TEXT, page_offset INTEGER,
  link_verified INTEGER, link_ok INTEGER, checked_at TEXT, sha256 TEXT,
  year INTEGER, month INTEGER, n_pages INTEGER, text_method TEXT, ocr_path TEXT,
  local_path TEXT, extractor_version TEXT, ingested_at TEXT);
CREATE TABLE pages (
  page_id INTEGER PRIMARY KEY, doc_id INTEGER, page_no INTEGER, n_blocks INTEGER, n_desig INTEGER,
  n_values INTEGER, n_parts INTEGER, priced_rows INTEGER, seq_run INTEGER, ad_score REAL,
  is_ad INTEGER, has_schematic INTEGER, classifier_version TEXT, w_pt REAL, h_pt REAL);
CREATE TABLE parts (part_id INTEGER PRIMARY KEY, part TEXT);
CREATE TABLE page_parts (
  page_id INTEGER, part_id INTEGER, n INTEGER, n_label INTEGER, conf TEXT, read_by TEXT,
  raw TEXT, boxes TEXT, near TEXT);

INSERT INTO parts (part_id, part) VALUES (1,'12AX7'), (2,'EL34'), (3,'2N3055');

-- Columns are named in every INSERT below. They were not at first, and a mis-counted value silently
-- pointed two rows at a part that does not exist, so the join dropped them and a whole source vanished
-- from the export with no error anywhere.

-- 1. downloaded, so its checksum says the link served this document. A real PDF with a page size.
INSERT INTO documents (doc_id, source, doc_key, role, title, public_url, page_url_tpl, page_offset,
                       link_verified, sha256, year, month, n_pages, text_method)
 VALUES (1,'esp','https://e.org/amp.pdf','schematic','ESP | 60W Amplifier - Elliott Sound Products',
         'https://e.org/amp.pdf','{url}#page={n}',0, 0,'aa11',1974,6,4,'ocr_boxes-1');
INSERT INTO pages (page_id, doc_id, page_no, n_parts, is_ad, has_schematic, w_pt, h_pt)
 VALUES (11,1,2,2,0,1,612,792);
INSERT INTO page_parts (page_id, part_id, n, conf, read_by, raw, boxes, near)
 VALUES (11,1,2,'high','ocr','12AX7','[[150,720,210,745]]','V1 R3 C12 xx Q4 R9');

-- 2. never downloaded, but a person checked the link by hand. No page size: the plain page link.
INSERT INTO documents (doc_id, source, doc_key, role, title, public_url, page_url_tpl, page_offset,
                       link_verified, link_ok, checked_at, year, n_pages, text_method)
 VALUES (2,'books','https://archive.org/details/radio-handbook','issue','Radio Handbook',
         'https://archive.org/details/radio-handbook','{url}/page/n{leaf}/mode/2up',12, 1,1,'2026-02-02',
         1959,300,'ocr_boxes-1');
INSERT INTO pages (page_id, doc_id, page_no, n_parts, is_ad, has_schematic)
 VALUES (21,2,5,1,0,0);
INSERT INTO page_parts (page_id, part_id, n, conf, read_by, raw, boxes, near)
 VALUES (21,2,1,'high','ocr','EL34','[[100,200,140,220]]','V2');

-- 3. a reader with no page anchor: the link is a search, which cannot point at the wrong page.
INSERT INTO documents (doc_id, source, doc_key, role, title, public_url, page_url_tpl, page_offset,
                       link_verified, year, n_pages, text_method)
 VALUES (3,'books','https://e.org/reader/tubes','issue','Tube Amplifier Handbook',
         'https://e.org/reader/tubes','{url}?q={q}',0, 0,1962,200,'text');
INSERT INTO pages (page_id, doc_id, page_no, n_parts, is_ad, has_schematic, w_pt, h_pt)
 VALUES (31,3,7,1,0,0,612,792);
INSERT INTO page_parts (page_id, part_id, n, conf, read_by, raw)
 VALUES (31,1,1,'high','text','12AX7');

-- 4. REFUSED: no checksum, nobody checked the link, and it is a location rather than a search.
INSERT INTO documents (doc_id, source, doc_key, role, title, public_url, link_verified, n_pages, text_method)
 VALUES (4,'esp','https://e.org/unchecked.html','project_page','Something',
         'https://e.org/unchecked.html',0,1,'text');
INSERT INTO pages (page_id, doc_id, page_no, n_parts, is_ad, has_schematic) VALUES (41,4,1,1,0,0);
INSERT INTO page_parts (page_id, part_id, n, conf, read_by, raw) VALUES (41,1,1,'high','text','12AX7');

-- 5. REFUSED: a mail-order price list. A part number here means somebody sold it, not that it was used.
INSERT INTO documents (doc_id, source, doc_key, role, title, public_url, page_url_tpl, page_offset,
                       link_verified, sha256, year, month, n_pages, text_method)
 VALUES (5,'wireless_world','https://e.org/ww-1974-06.pdf','issue','Wireless World June 1974',
         'https://e.org/ww-1974-06.pdf','{url}#page={n}',0, 0,'bb22',1974,6,120,'ocr_boxes-1');
INSERT INTO pages (page_id, doc_id, page_no, n_parts, priced_rows, ad_score, is_ad, has_schematic, w_pt, h_pt)
 VALUES (51,5,81,40,55,0.97,1,0,595,842);
INSERT INTO page_parts (page_id, part_id, n, conf, read_by, raw, boxes)
 VALUES (51,2,9,'high','ocr','EL34','[[80,100,120,115]]');

-- 6. REFUSED: read with low confidence. The same page also holds a good reading, which is kept.
INSERT INTO pages (page_id, doc_id, page_no, n_parts, is_ad, has_schematic, w_pt, h_pt)
 VALUES (52,5,47,3,0,1,595,842);
INSERT INTO page_parts (page_id, part_id, n, conf, read_by, raw, boxes, near)
 VALUES (52,3,1,'medium','ocr','2N3O55','[[300,400,350,420]]','Q1');
INSERT INTO page_parts (page_id, part_id, n, conf, read_by, raw, boxes, near)
 VALUES (52,1,1,'high','ocr','12AX7','[[300,500,350,520]]','V1 V2');

-- 7. a figure hanging off a project page: its own row, and its parent's name to fall back on.
INSERT INTO documents (doc_id, source, doc_key, role, parent_doc_id, public_url, link_verified,
                       sha256, n_pages, text_method)
 VALUES (7,'esp','https://e.org/fig/amp-psu.gif','figure',1,'https://e.org/fig/amp-psu.gif',0,
         'cc33',1,'ocr_boxes-1');
INSERT INTO pages (page_id, doc_id, page_no, n_parts, is_ad, has_schematic) VALUES (71,7,1,1,0,1);
INSERT INTO page_parts (page_id, part_id, n, conf, read_by, raw, boxes, near)
 VALUES (71,3,1,'high','ocr','2N3055','[[10,20,60,45]]','Q1 Q2');

-- 8. WITHDRAWN by tests/schematics/test_export.py: published once, then taken down. Its <title> is the
-- default its CMS left behind, so the name has to come from the URL.
INSERT INTO documents (doc_id, source, doc_key, role, title, public_url, page_url_tpl, page_offset,
                       link_verified, sha256, n_pages, text_method)
 VALUES (8,'esp','https://e.org/gone.pdf','schematic','index.html',
         'https://e.org/gone.pdf','{url}#page={n}',0, 0,'dd44',2,'ocr_boxes-1');
INSERT INTO pages (page_id, doc_id, page_no, n_parts, is_ad, has_schematic, w_pt, h_pt)
 VALUES (81,8,1,1,0,1,612,792);
INSERT INTO page_parts (page_id, part_id, n, conf, read_by, raw, boxes)
 VALUES (81,1,1,'high','ocr','12AX7','[[200,300,240,320]]');
