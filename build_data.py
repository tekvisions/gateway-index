#!/usr/bin/env python3
"""The Gateway Index — recompute the living index of LLM gateways, proxies & routers from live
GitHub signals, and write data.json + SEO (sitemap, rss, robots, llms.txt).

Scope = the infrastructure that sits BETWEEN apps and LLM providers: gateways & proxies
(LiteLLM, Portkey, one-api), model routers (RouteLLM, semantic-router), unified multi-provider
SDKs, caching/cost layers, and observability gateways. NOT inference engines (vllm/ollama →
local-llm-index), NOT agent/app frameworks, NOT pure observability (langfuse → eval-index),
NOT RAG/vector. Gathered, deduped, FILTERED (precision over recall), categorized, scored.

Only the GitHub *search* payload is used. Env: GITHUB_TOKEN (required for a usable rate limit).
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.github.com"
SITE_URL = "https://gateway.kymatalabs.com"   # fixed to the real alias after first deploy
SITE_NAME = "The Gateway Index"

QUERIES = [
    "topic:llm-gateway stars:>20",
    "topic:ai-gateway stars:>20",
    "topic:llm-proxy stars:>20",
    "topic:llm-router stars:>20",
    "topic:model-routing stars:>20",
    "topic:semantic-router stars:>40",
    "topic:litellm stars:>20",
    "topic:openai-proxy stars:>40",
    "llm gateway in:name,description stars:>60",
    "ai gateway in:name,description stars:>120",
    "llm router in:name,description stars:>60",
    "openai api proxy in:name,description stars:>120",
    "llm proxy in:name,description stars:>60",
    "unified llm api in:name,description stars:>60",
    "multi provider llm in:name,description stars:>50",
    "llm load balancing in:name,description stars:>40",
    "openai compatible proxy in:name,description stars:>80",
    "model router llm in:name,description stars:>40",
]


def token() -> str:
    return (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()


HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "gateway-index"}
if token():
    HEADERS["Authorization"] = f"Bearer {token()}"

_GATE_TOPICS = {"llm-gateway", "ai-gateway", "llm-proxy", "llm-router", "model-routing",
                "semantic-router", "litellm", "llmops", "openai-proxy", "llm-api",
                "multi-llm", "ai-proxy", "model-gateway", "llm-routing",
                "openai-compatible", "llm-load-balancing", "prompt-caching"}
_GATE_PHRASES = re.compile(
    r"\b(llm gateway|ai gateway|gateway for (llm|ai|openai)|llm proxy|proxy for (openai|llm)"
    r"|llm router|model rout(er|ing)|route (between|to) (llm|model)|openai([- ]api)? proxy"
    r"|openai[- ]compatible (api|proxy|gateway|endpoint)|unified (llm|ai)? ?api|unified interface"
    r"|multi[- ]?(provider|model|llm)|llm load balanc|semantic rout|drop[- ]in replacement for openai"
    r"|one[- ]?api|cost (tracking|control|optimi[sz]ation) for llm|prompt caching|llm caching"
    r"|call (any|every|100\+?) (llm|model)|access (any|every|100\+?) (llm|model)|llm abstraction)\b", re.I)

# Inference engines (local-llm-index), agent/app frameworks, chat UIs, pure observability/eval
# (eval-index), RAG/vector, official provider SDKs, and sibling-index repos that match but aren't
# gateway/proxy/router INFRASTRUCTURE.
# _ALLOW wins over _ANTI/_DENY false-positives (the unambiguous core of the category).
_ALLOW = {
    "berriai/litellm", "kong/kong", "quantumnous/new-api", "apache/apisix", "higress-group/higress",
    "portkey-ai/gateway", "vllm-project/semantic-router", "maximhq/bifrost", "kgateway-dev/kgateway",
    "envoyproxy/ai-gateway", "krakend/krakend-ce", "katanemo/plano", "agentgateway/agentgateway",
    "tensorzero/tensorzero", "theopenco/llmgateway", "songquanpeng/one-api", "traceloop/hub",
    "helicone/ai-gateway", "lm-sys/routellm", "kenyony/openai-forward", "nvidia-ai-blueprints/llm-router",
    "apiparklab/apipark", "aws-samples/bedrock-access-gateway", "adaline/gateway", "ibm/mcp-context-forge",
    "trylonai/gateway", "stacklok/codegate", "easychen/openai-api-proxy", "supercorp-ai/supergateway",
    "atopos31/llmio", "nya-foundation/nyaproxy", "1b5d/llm-api",
}
_DENY = {
    # inference engines (local-llm-index), agent/app frameworks, chat UIs
    "vllm-project/vllm", "ollama/ollama", "ggerganov/llama.cpp", "ggml-org/llama.cpp",
    "oobabooga/text-generation-webui", "sgl-project/sglang", "lm-sys/fastchat",
    "lmstudio-ai/lms", "huggingface/text-generation-inference", "mudler/localai", "intentee/paddler",
    "langchain-ai/langchain", "run-llama/llama_index", "langgenius/dify", "microsoft/autogen",
    "crewaiinc/crewai", "open-webui/open-webui", "lobehub/lobe-chat", "mckaywrigley/chatbot-ui",
    "langfuse/langfuse", "arize-ai/phoenix", "n8n-io/n8n", "flowiseai/flowise",
    "openai/openai-python", "openai/openai-node", "anthropics/anthropic-sdk-python",
    "vercel/ai", "transformeroptimus/superagi", "danny-avila/librechat",
    "labring/fastgpt", "chatgptweb/chatgpt-web",
    # agent toolkits/servers/platforms, BaaS, auth/IAM, eval/benchmarks, settings, personas — clear bleed
    "earendil-works/pi", "butterbase-ai/butterbase", "casdoor/casdoor", "insforge/insforge",
    "natebjones-projects/ob1", "future-agi/future-agi", "octelium/octelium",
    "litellm-labs/litellm-agent-platform", "nextlevelbuilder/goclaw", "freestylefly/wesight",
    "fareedkhan-dev/all-agentic-architectures", "moltis-org/moltis", "intellicia-public/parastore",
    "k-dense-ai/k-dense-byok", "aqbot-desktop/aqbot", "toby-bridges/api-relay-audit", "liaohch3/claude-tap",
    "porunc/codewiki", "0xnyk/council-of-high-intelligence", "vybestack/llxprt-code",
    "morphik-org/morphik-core", "gobii-ai/gobii-platform", "kardolus/chatgpt-cli",
    "ahmet-dedeler/ai-llm-comparison", "dreadnode/rigging", "quanz827/zexus", "arafatahmed-2m/2m-code",
    "barun-saha/slide-deck-ai", "nuxt-ui-templates/chat", "feiskyer/claude-code-settings",
    "feiskyer/codex-settings", "vercel-labs/coding-agent-template", "vllora/vllora",
    "duelion/homebox-companion", "codeking-ai/cligate", "qjhwc/paperforge", "open-bias/open-bias",
    "thesyart/emperor-agent", "iqaicom/adk-ts", "antiv/mate", "prometheus-eval/prometheus-eval",
    "centerforaisafety/wmdp", "withmartian/routerbench", "routeworks/routerarena", "mr-karan/hodor",
    "xeloxa/temodar-agent", "yjg30737/pyqt-openai", "atinux/atidraw", "sno-ai/llmix",
    "m7mdhka/pydantic-ai-production-ready-template", "syrin-labs/syrin-harness", "ragavrida/mmcp",
    "phil65/agentpool", "kenza-ai/sagify", "bmd1905/chatopsllm", "langfuse/oss-llmops-stack",
    "ihabkhaled/clawai", "choihyunsus/n2-qln", "smkrv/ha-text-ai", "raphaelmansuy/edgecrab",
    "strands-agents/tools", "strands-agents/samples", "strands-agents/docs", "strands-agents/agent-builder",
    "strands-agents/harness-sdk", "lispking/agent-io", "cognesy/instructor-php", "mnfst/manifest",
    "fus3n/gem-assist", "zhalice2011/proxyllm", "w8123/enterpriseagentframework", "hashstacs-global/enclaws",
    "kkddytd/claude-api", "qjhwc/paperforge", "vibheksoni/uniclaudeproxy",
} - _ALLOW
_ANTI = re.compile(
    r"\b(awesome|curated list|tutorial|course|roadmap|cheat ?sheet|paper[- ]?(list|survey)"
    r"|reading list|book\b|from scratch|inference (engine|server)|serve (llms|models) locally"
    r"|run (llms|models) locally|fine[- ]?tun|quantiz|vector (database|db|store|search)|rag\b"
    r"|retrieval[- ]augmented|embedding model|agent (framework|toolkit|workspace|server|builder|orchestrat|harness|samples)"
    r"|chat ?(ui|bot clone)|chatgpt clone|\bmcp server\b|text[- ]to[- ]image|stable diffusion|\btts\b"
    r"|knowledge (base|platform)|workflow automation|no[- ]code|web scrap|prompt engineering guide"
    r"|account[- ]?pool|账号池|反代|加速|reverse[- ]?fast|unlimited free|free (ai coding|unlimited|llm channel)"
    r"|coding[- ]plan|switch between claude|wordpress|home assistant|\brevit\b|slide deck|co[- ]scientist"
    r"|council of|reliability harness|routerbench|routerarena|llmops stack|digital employee|数字员工"
    r"|backend[- ]as[- ]a[- ]service|identity and access|academic paper|paper writing)\b", re.I)


def gh(url: str, *, retries: int = 4):
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (403, 429):
                reset = e.headers.get("X-RateLimit-Reset")
                wait = 5 * (attempt + 1)
                if reset:
                    try:
                        wait = max(wait, min(60, int(reset) - int(time.time()) + 2))
                    except ValueError:
                        pass
                print(f"  rate-limited — sleeping {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if 500 <= e.code < 600:
                time.sleep(3 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(3 * (attempt + 1))
    if last:
        raise last
    raise RuntimeError(f"gh failed: {url}")


def search(q: str, per_page: int = 40) -> list[dict]:
    url = (f"{API}/search/repositories?q={urllib.parse.quote(q)}"
           f"&sort=stars&order=desc&per_page={per_page}")
    try:
        return gh(url).get("items", [])
    except Exception as e:
        print(f"  query failed [{q}]: {e}", file=sys.stderr)
        return []


def is_gateway(r: dict) -> bool:
    full = (r.get("full_name") or "").lower()
    if full in _ALLOW:
        return True
    if full in _DENY:
        return False
    name = r.get("name") or ""
    desc = r.get("description") or ""
    if _ANTI.search(f"{name} {desc}"):
        return False
    topics = {t.lower() for t in (r.get("topics") or [])}
    if topics & _GATE_TOPICS:
        return True
    return bool(_GATE_PHRASES.search(f"{name} {desc}"))


def categorize(r: dict) -> str:
    # base specialized buckets on name+desc (topics are noisy for multi-feature flagships);
    # "Gateways & Proxies" is the default catch-all.
    nd = f"{(r.get('name') or '').lower()} {(r.get('description') or '').lower()}"
    if re.search(r"awesome|curated|\blist of\b|directory|catalog", nd):
        return "Collections"
    if re.search(r"\brouter\b|\brouting\b|route (requests|traffic|prompts)?\s*(to|between|across)"
                 r"|routellm|semantic[- ]?router|notdiamond|model selection|picks? the (best|right) (llm|model)", nd):
        return "Routers"
    if re.search(r"observ|tracing|telemetry|openllmetry|opentelemetry|\bhelicone\b|lunary|monitor", nd):
        return "Observability Gateways"
    if re.search(r"(ai|llm|api) gateway|proxy server|gateway (server|to call|for)|reverse proxy"
                 r"|openai[- ]?compatible (api )?(proxy|gateway|endpoint)", nd):
        return "Gateways & Proxies"
    if re.search(r"\bcach|cost[- ](saving|control|tracking|optimi|aware)|cut .*cost|\bbudget\b|spend(ing)?", nd):
        return "Caching & Cost"
    if re.search(r"\bsdk\b|client library|unified \w* ?(api|interface|client)|aisuite|abstraction layer"
                 r"|(python|typescript|go|rust) (library|package) to (use|call|access)", nd):
        return "Multi-Provider SDKs"
    if re.search(r"self[- ]?host|enterprise|aggregat|distribution|分发|多渠道|管理|hub for|admin (panel|dashboard)", nd):
        return "Self-Hosted Platforms"
    return "Gateways & Proxies"


def days_since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 86400.0
    except ValueError:
        return None


def momentum(r: dict, max_stars: int) -> int:
    stars = r.get("stargazers_count", 0) or 0
    star_norm = math.log10(stars + 1) / math.log10(max(max_stars, 10) + 1)
    pushed = days_since(r.get("pushed_at"))
    recency = 0.2 if pushed is None else max(0.0, 1.0 - max(0.0, pushed) / 180.0)
    created = days_since(r.get("created_at"))
    young = (1.0 - created / 120.0) if (created is not None and created < 120 and stars >= 20) else 0.0
    return max(1, min(100, round((0.55 * star_norm + 0.32 * recency + 0.13 * young) * 100)))


def slugify(full_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", full_name.lower()).strip("-")


def build_items() -> list[dict]:
    seen: dict[str, dict] = {}
    for q in QUERIES:
        for r in search(q):
            full = r.get("full_name")
            if full and full not in seen and is_gateway(r):
                seen[full] = r
        time.sleep(0.7)
    raw = list(seen.values())
    max_stars = max((r.get("stargazers_count", 0) or 0) for r in raw) if raw else 10
    items = []
    for r in raw:
        owner = r.get("owner") or {}
        items.append({
            "name": r.get("name", ""), "full_name": r.get("full_name", ""),
            "slug": slugify(r.get("full_name", "")), "url": r.get("html_url", ""),
            "owner": owner.get("login", ""), "owner_avatar": owner.get("avatar_url", ""),
            "stars": r.get("stargazers_count", 0) or 0, "forks": r.get("forks_count", 0) or 0,
            "open_issues": r.get("open_issues_count", 0) or 0, "language": r.get("language") or "",
            "license": ((r.get("license") or {}) or {}).get("spdx_id") or "",
            "pushed_at": r.get("pushed_at"), "created_at": r.get("created_at"),
            "description": (r.get("description") or "").strip(), "topics": r.get("topics") or [],
            "category": categorize(r), "momentum": momentum(r, max_stars),
        })
    items.sort(key=lambda x: (x["momentum"], x["stars"]), reverse=True)
    for i, it in enumerate(items, 1):
        it["rank"] = i
    return items


def write_json(items: list[dict]) -> dict:
    cats: dict[str, int] = {}
    for it in items:
        cats[it["category"]] = cats.get(it["category"], 0) + 1
    data = {"generated_at": datetime.now(timezone.utc).isoformat(), "count": len(items),
            "categories": [{"name": k, "count": v} for k, v in sorted(cats.items(), key=lambda x: -x[1])],
            "items": items}
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def write_seo(data: dict) -> None:
    items = data["items"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [f"  <url><loc>{SITE_URL}/</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for it in items:
        urls.append(f"  <url><loc>{SITE_URL}/p/{it['slug']}/</loc><lastmod>{now}</lastmod>"
                    f"<changefreq>weekly</changefreq><priority>0.6</priority></url>")
    open(os.path.join(HERE, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>\n")
    open(os.path.join(HERE, "robots.txt"), "w", encoding="utf-8").write(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")

    def esc(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    rss_items = [
        f"    <item><title>{esc(it['full_name'])} — momentum {it['momentum']}</title>"
        f"<link>{SITE_URL}/p/{it['slug']}/</link><guid isPermaLink=\"false\">{esc(it['full_name'])}</guid>"
        f"<description>{esc(it['description'][:300])}</description></item>" for it in items[:30]]
    open(os.path.join(HERE, "rss.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0">\n  <channel>\n'
        f"    <title>{SITE_NAME}</title>\n    <link>{SITE_URL}</link>\n"
        "    <description>The living index of LLM gateways, proxies & routers — the infrastructure between apps and LLM providers.</description>\n"
        + "\n".join(rss_items) + "\n  </channel>\n</rss>\n")

    lines = [f"# {SITE_NAME}", "",
             "> The living index of LLM gateways, proxies & routers — the infrastructure that sits",
             "> between apps and LLM providers — ranked daily by GitHub momentum.", "",
             f"Updated: {data['generated_at']}", f"Tools indexed: {data['count']}", "",
             "## Top LLM gateways, proxies & routers by momentum", ""]
    for it in items[:40]:
        lines.append(f"- [{it['full_name']}]({it['url']}) — momentum {it['momentum']}, "
                     f"⭐{it['stars']} — {it['category']} — {it['description'][:100]}")
    open(os.path.join(HERE, "llms.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main() -> int:
    if not token():
        print("WARNING: no GITHUB_TOKEN — low rate limit, partial results", file=sys.stderr)
    items = build_items()
    if not items:
        print("ERROR: no gateway tools found — refusing to write empty data.json", file=sys.stderr)
        return 1
    data = write_json(items)
    write_seo(data)
    print(f"wrote data.json: {len(items)} gateway tools across {len(data['categories'])} categories")
    print("  top 5:", ", ".join(f"{it['full_name']}({it['momentum']})" for it in items[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
