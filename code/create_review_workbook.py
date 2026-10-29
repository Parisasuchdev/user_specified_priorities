"""Build a manual review XLSX from saved responses using only the standard library."""
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/official_v1'
OUTPUT = BASE / 'official_collection_review.xlsx'
SCHEMAS = {
'Runs': 'run_id provider model condition repetition prompt status claude_rounds submitted_at_utc result_saved_at_utc report_word_count query_count returned_source_records unique_returned_urls citation_count unique_cited_urls open_page_count find_in_page_count web_fetch_count review_status review_note',
'Reports': 'run_id provider condition repetition report_text word_count character_count citation_count review_status review_note',
'Queries': 'query_id run_id provider condition repetition query_order search_action_id query_text navigational_flag include_query review_note',
'Returned_Sources': 'source_record_id run_id provider condition search_action_id query_id source_order url_raw url_normalized domain title cited_anywhere review_note',
'Citations': 'citation_id run_id provider condition citation_order url_raw url_normalized domain title cited_text start_index end_index report_unit_id mapping_reviewed review_note',
'Report_Units': 'report_unit_id run_id provider condition repetition unit_order section_heading unit_type unit_text citation_present citation_count include_unit split_reviewed review_note',
'Tool_Actions': 'action_id run_id provider condition action_order api_round action_type query_text url find_pattern',
'Usage': 'run_id provider condition api_round input_tokens cached_tokens cache_write_tokens output_tokens reasoning_or_thinking_tokens total_tokens web_search_requests web_fetch_requests service_tier',
}
SHEETS = {k: [] for k in SCHEMAS}

def normalize(url):
    if not url:
        return ''
    p = urlsplit(url)
    # Only remove known tracking parameters; retain functional parameters and path case.
    query = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in {'gclid','fbclid','msclkid'}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(query), ''))

def unit_spans(text):
    """Provisional units with exact report offsets. Tables kept whole for review."""
    heading = ''
    spans = []
    for match in re.finditer(r'[^\n]+', text):
        line = match.group(); start = match.start()
        if not line.strip():
            continue
        if re.match(r'^\s*#{1,6}\s', line):
            heading = line.strip(); typ = 'heading'; parts = [(0,len(line))]
        elif re.match(r'^\s*\|', line):
            typ = 'table_row'; parts = [(0,len(line))]
        elif re.match(r'^\s*(?:[-*+]\s|\d+[.)]\s)', line):
            typ = 'bullet'; parts = [(0,len(line))]
        elif re.match(r'^\s*[-*_]{3,}\s*$',line):
            typ = 'excluded'; parts = [(0,len(line))]
        else:
            typ = 'sentence'
            masked = re.sub(r'https?://[^\s)]+', lambda m: 'x'*len(m.group()),line)
            boundaries = [0] + [m.end() for m in re.finditer(r'[.!?]["”\x27*]*\s+(?=[A-Z0-9*“])', masked)] + [len(line)]
            parts = list(zip(boundaries, boundaries[1:]))
        for a,b in parts:
            if line[a:b].strip():
                spans.append((start+a,start+b,heading,typ,line[a:b]))
    return spans

def extract():
    specs = json.loads((BASE/'collection.json').read_text())['runs']
    for spec in specs:
        run = spec['run_id']; folder = BASE/'runs'/run
        meta = json.loads((folder/'metadata.json').read_text())
        report = (folder/'final_report.txt').read_text()
        common = {k: meta[k] for k in ['run_id','provider','condition','repetition']}
        local = {k: [] for k in ['Queries','Returned_Sources','Citations','Tool_Actions']}
        texts = []; unit_pieces = []; citation_spans = []; action_queries = {}; text_offset = 0; last_was_text = False
        rounds = sorted(folder.glob('response*.json'))
        for round_number,path in enumerate(rounds,1):
            w = json.loads(path.read_text())
            r = w['response']['body'] if meta['provider']=='openai' else w['result']['message']
            u = r.get('usage',{}); details = u.get('input_tokens_details',{}); out = u.get('output_tokens_details',{}); tool_usage = u.get('server_tool_use',{})
            SHEETS['Usage'].append(dict(common, api_round=round_number,input_tokens=u.get('input_tokens',''),
                cached_tokens=details.get('cached_tokens',u.get('cache_read_input_tokens','')),
                cache_write_tokens=details.get('cache_write_tokens',u.get('cache_creation_input_tokens','')),
                output_tokens=u.get('output_tokens',''),reasoning_or_thinking_tokens=out.get('reasoning_tokens',out.get('thinking_tokens','')),
                total_tokens=u.get('total_tokens',''),web_search_requests=tool_usage.get('web_search_requests',''),
                web_fetch_requests=tool_usage.get('web_fetch_requests',''),service_tier=u.get('service_tier',r.get('service_tier',''))))
            for block in r.get('output',r.get('content',[])):
                typ = block['type']; action = None; query_strings = []; sources = []
                if typ not in {'text', 'output_text', 'message'}:
                    last_was_text = False
                if typ == 'web_search_call':
                    a=block['action']; action=dict(a); query_strings=a.get('queries', [a['query']] if a.get('query') else [])
                    sources=a.get('sources',[])
                elif typ == 'server_tool_use':
                    a=block['input']; action=dict(a,type={'web_search':'search','web_fetch':'web_fetch'}.get(block['name'],block['name']))
                    query_strings=[a['query']] if a.get('query') else []
                if action is not None:
                    aid=block.get('id',f'{run}_A{len(local["Tool_Actions"])+1:03}')
                    local['Tool_Actions'].append(dict(common,action_id=aid,action_order=len(local['Tool_Actions'])+1,
                        api_round=round_number,action_type=action['type'],query_text='\n'.join(query_strings),
                        url=action.get('url',''),find_pattern=action.get('pattern','')))
                    qids=[]
                    for query in query_strings:
                        order=len(local['Queries'])+1; qid=f'{run}_Q{order:03}'; qids.append(qid)
                        local['Queries'].append(dict(common,query_id=qid,query_order=order,search_action_id=aid,
                            query_text=query,navigational_flag='',include_query=1,
                            review_note='Navigational flag intentionally blank; apply your manual rule.'))
                    action_queries[aid]=qids
                    for order,source in enumerate(sources,1):
                        add_source(local,common,source,aid,qids[0] if len(qids)==1 else '',order)
                if typ == 'web_search_tool_result' and isinstance(block.get('content'),list):
                    aid=block.get('tool_use_id',''); qids=action_queries.get(aid,[])
                    for order,source in enumerate(block['content'],1):
                        if source.get('type')=='web_search_result':
                            add_source(local,common,source,aid,qids[0] if len(qids)==1 else '',order)
                parts=block.get('content',[]) if typ=='message' else [block]
                for part in parts:
                    if part.get('type') not in {'text','output_text'}:
                        continue
                    text=part['text']
                    separator = '\n\n' if texts and (meta['provider']=='openai' or not last_was_text) else ''
                    unit_pieces.extend([separator, text]); text_offset += len(separator)
                    texts.append(text)
                    for cite in (part.get('annotations') or [])+(part.get('citations') or []):
                        order=len(local['Citations'])+1
                        raw=cite.get('url',''); normalized=normalize(raw)
                        local['Citations'].append(dict(common,citation_id=f'{run}_C{order:03}',citation_order=order,
                            url_raw=raw,url_normalized=normalized,domain=urlsplit(raw).netloc.lower(),title=cite.get('title',''),
                            cited_text=cite.get('cited_text',''),start_index=cite.get('start_index',''),end_index=cite.get('end_index',''),
                            report_unit_id='',mapping_reviewed=0,review_note=''))
                        if meta['provider']=='openai' and isinstance(cite.get('start_index'),int):
                            citation_spans.append((order-1,text_offset+cite['start_index'],text_offset+cite['end_index']))
                        else:
                            # Claude cited_text is evidence, not report text: map using the attributed text block.
                            citation_spans.append((order-1,text_offset,text_offset+len(text)))
                    text_offset+=len(text); last_was_text = True
        assert '\n\n'.join(texts)==report, f'Report reconstruction mismatch: {run}'
        # Rejoin adjacent Claude text blocks so citation boundaries do not create false sentences.
        spans=unit_spans(''.join(unit_pieces)); units=[]
        for i,(a,b,heading,typ,text) in enumerate(spans,1):
            uid=f'{run}_U{i:04}'
            units.append(dict(common,report_unit_id=uid,unit_order=i,section_heading=heading,unit_type=typ,unit_text=text,
                citation_present=0,citation_count=0,include_unit=0 if typ in {'heading','excluded','table_row'} else 1,
                split_reviewed=0,review_note='Provisional split.' if typ!='table_row' else 'Excluded pending your frozen table-unit rule.'))
        for ci,a,b in citation_spans:
            matches=[i for i,(ua,ub,*_) in enumerate(spans) if a<ub and b>ua]
            citation=local['Citations'][ci]
            if matches:
                citation['report_unit_id']='; '.join(units[i]['report_unit_id'] for i in matches)
                citation['review_note']='Provisional mapping from '+('annotation offsets.' if meta['provider']=='openai' else 'attributed report text block; cited_text is a source excerpt.')
                for i in matches:
                    units[i]['citation_present']=1; units[i]['citation_count']+=1
            else:
                citation['review_note']='Unmapped; review raw response.'
        cited={c['url_normalized'] for c in local['Citations'] if c['url_normalized']}
        for source in local['Returned_Sources']:
            source['cited_anywhere']=int(source['url_normalized'] in cited)
        counts=Counter(a['action_type'] for a in local['Tool_Actions'])
        words=len(report.split())
        SHEETS['Runs'].append(dict(meta,report_word_count=words,query_count=len(local['Queries']),
            returned_source_records=len(local['Returned_Sources']),unique_returned_urls=len({s['url_normalized'] for s in local['Returned_Sources'] if s['url_normalized']}),
            citation_count=len(local['Citations']),unique_cited_urls=len(cited),open_page_count=counts['open_page'],
            find_in_page_count=counts['find_in_page'],web_fetch_count=counts['web_fetch'],review_status='Pending',review_note=''))
        SHEETS['Reports'].append(dict(common,report_text=report,word_count=words,character_count=len(report),
            citation_count=len(local['Citations']),review_status='Pending',review_note=''))
        SHEETS['Report_Units'].extend(units)
        for name,rows in local.items():
            SHEETS[name].extend(rows)

def add_source(local,common,source,aid,qid,order):
    raw=source.get('url','')
    local['Returned_Sources'].append(dict(common,source_record_id=f'{common["run_id"]}_S{len(local["Returned_Sources"])+1:04}',
        search_action_id=aid,query_id=qid,source_order=order,url_raw=raw,url_normalized=normalize(raw),
        domain=urlsplit(raw).netloc.lower(),title=source.get('title',''),cited_anywhere=0,review_note=''))

def col(n):
    s=''
    while n:
        n,r=divmod(n-1,26);s=chr(65+r)+s
    return s

def cell(ref,value,style):
    if isinstance(value,bool):value=int(value)
    if isinstance(value,(int,float)):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    value=str(value) if value is not None else ''
    assert len(value)<=32767, f'Excel cell too long: {ref}'
    value=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',value)
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'

def write_xlsx():
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with zipfile.ZipFile(OUTPUT,'w',zipfile.ZIP_DEFLATED) as z:
        overrides=''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,9))
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+overrides+'</Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i,name in enumerate(SCHEMAS,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,9))+'<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml',f'<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF234E70"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        manual={'review_status','review_note','navigational_flag','include_query','mapping_reviewed','include_unit','split_reviewed'}
        for sheet_number,(name,header) in enumerate(SCHEMAS.items(),1):
            fields=header.split(); rows=SHEETS[name];last=f'{col(len(fields))}{len(rows)+1}'
            columns=[]
            for i,field in enumerate(fields,1):
                width=100 if field in {'report_text','unit_text'} else 65 if field in {'prompt','query_text','cited_text','url_raw','url_normalized'} else 45 if field in {'review_note','section_heading','title'} else 25
                columns.append(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>')
            data=['<row r="1" ht="32" customHeight="1">'+''.join(cell(f'{col(i)}1',f,1) for i,f in enumerate(fields,1))+'</row>']
            for ri,row in enumerate(rows,2):
                height=160 if name=='Reports' else 65 if name=='Report_Units' else 45
                data.append(f'<row r="{ri}" ht="{height}" customHeight="1">'+''.join(cell(f'{col(i)}{ri}',row.get(f,''),3 if f in manual else 2) for i,f in enumerate(fields,1))+'</row>')
            validations=[]
            for i,f in enumerate(fields,1):
                options='"Pending,Reviewed"' if f=='review_status' else '"0,1"' if f in manual-{'review_note'} else None
                if options:
                    validations.append(f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="{col(i)}2:{col(i)}{len(rows)+1}"><formula1>{escape(options)}</formula1></dataValidation>')
            validation=f'<dataValidations count="{len(validations)}">'+''.join(validations)+'</dataValidations>' if validations else ''
            z.writestr(f'xl/worksheets/sheet{sheet_number}.xml',f'<worksheet xmlns="{ns}"><dimension ref="A1:{last}"/><sheetViews><sheetView workbookViewId="0"><pane xSplit="1" ySplit="1" topLeftCell="B2" activePane="bottomRight" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/><cols>'+''.join(columns)+'</cols><sheetData>'+''.join(data)+f'</sheetData><autoFilter ref="A1:{last}"/>'+validation+'</worksheet>')

def main():
    extract(); write_xlsx()
    print(OUTPUT)
    print(json.dumps({k:len(v) for k,v in SHEETS.items()},indent=2))

if __name__=='__main__':main()
