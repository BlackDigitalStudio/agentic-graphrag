import sys, json

logfile = sys.argv[1]
with open(logfile, 'r', encoding='utf-8') as f:
    text = f.read()

sections = text.split('=' * 80)
for section in sections:
    if 'CHUNK:' not in section or 'LLM RESPONSE' not in section:
        continue

    # Chunk ID
    for line in section.split('\n'):
        if 'CHUNK:' in line:
            chunk_id = line.strip()[:50]
            break

    # Raw JSON from LLM response
    resp_start = section.find('--- LLM RESPONSE')
    parsed_start = section.find('--- PARSED RESULT')
    if resp_start < 0 or parsed_start < 0:
        print(f"{chunk_id}: MISSING SECTIONS")
        continue

    response = section[resp_start:parsed_start]
    parsed_section = section[parsed_start:]

    # Parse raw response (skip <think> block)
    think_end = response.find('</think>')
    search_from = think_end + 8 if think_end >= 0 else 0

    raw_json_start = response.find('{', search_from)
    raw_json_end = response.rfind('}')

    raw_ent_count = 0
    raw_edge_count = 0
    raw_names = []

    if raw_json_start >= 0 and raw_json_end > raw_json_start:
        try:
            raw = json.loads(response[raw_json_start:raw_json_end+1])
            raw_ent_count = len(raw.get('entities', []))
            raw_edge_count = len(raw.get('edges', []))
            raw_names = [e.get('name', '?') for e in raw.get('entities', [])]
        except:
            raw_ent_count = -1

    # Parse parsed result
    p_json_start = parsed_section.find('{')
    p_json_end = parsed_section.rfind('}')

    parsed_ent_count = 0
    parsed_edge_count = 0
    parsed_names = []

    if p_json_start >= 0 and p_json_end > p_json_start:
        try:
            parsed = json.loads(parsed_section[p_json_start:p_json_end+1])
            parsed_ent_count = len(parsed.get('entities', []))
            parsed_edge_count = len(parsed.get('edges', []))
            parsed_names = [e.get('name', '?') for e in parsed.get('entities', [])]
        except:
            parsed_ent_count = -1

    match = "OK" if raw_ent_count == parsed_ent_count and raw_edge_count == parsed_edge_count else "MISMATCH"
    print(f"{chunk_id} | {match} | raw: {raw_ent_count}e {raw_edge_count}ed | parsed: {parsed_ent_count}e {parsed_edge_count}ed")

    if raw_names != parsed_names:
        missing_in_parsed = set(raw_names) - set(parsed_names)
        extra_in_parsed = set(parsed_names) - set(raw_names)
        if missing_in_parsed:
            print(f"  LOST: {missing_in_parsed}")
        if extra_in_parsed:
            print(f"  EXTRA: {extra_in_parsed}")
