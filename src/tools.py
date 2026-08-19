import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import ssl
import time
import re
from agents import function_tool

# Global flag to track if search was called (for evaluation)
_web_search_called = False

@function_tool
def search_web(query: str) -> str:
    """Search the web for wildlife sanctuaries, national parks, environmental policies, statistics, legal orders, and news updates in Assam, India.
    
    IMPORTANT: Provide a short, keyword-based query (e.g., 'Kaziranga ESZ news' or 'Pranab Doley arrest') rather than a full sentence or question to ensure DuckDuckGo returns results.
    
    Args:
        query: The optimized search keywords.
    """
    global _web_search_called
    _web_search_called = True
    
    print(f"[Search Tool] Executing query: '{query}'")
    
    # 1. Try Google News RSS Search first (highly robust, never ratelimited, returns fresh news)
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        )
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            xml_data = response.read()
        
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        if items:
            output = []
            for i, item in enumerate(items[:8], 1):
                title = item.find("title").text if item.find("title") is not None else "No Title"
                link = item.find("link").text if item.find("link") is not None else "No Link"
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                desc = item.find("description").text if item.find("description") is not None else ""
                clean_desc = re.sub('<[^<]+?>', '', desc) if desc else ""
                output.append(f"{i}. Title: {title}\n   Link: {link}\n   Date: {pub_date}\n   Snippet: {clean_desc[:250]}\n")
            print(f"[Search Tool] Successful Google News RSS retrieval ({len(items)} items found)")
            return "\n".join(output)
    except Exception as e:
        print(f"[Search Tool] Google News RSS query failed: {e}")
        
    # 2. Fallback to DuckDuckGo search if RSS fails
    print("[Search Tool] Falling back to DuckDuckGo search...")
    from duckduckgo_search import DDGS
    exceptions = []
    
    for method_name in ["news", "text"]:
        for attempt in range(2):
            try:
                with DDGS() as ddgs:
                    if method_name == "news":
                        results = list(ddgs.news(query, max_results=5))
                    else:
                        results = list(ddgs.text(query, max_results=5))
                    
                    if results:
                        output = []
                        for i, r in enumerate(results, 1):
                            title = r.get('title') or 'No Title'
                            href = r.get('href') or r.get('url') or 'No Link'
                            body = r.get('body') or r.get('snippet') or r.get('text') or ''
                            output.append(f"{i}. Title: {title}\n   Link: {href}\n   Snippet: {body}\n")
                        print(f"[Search Tool] Successful DuckDuckGo {method_name} search on attempt {attempt+1}")
                        return "\n".join(output)
            except Exception as e:
                err_str = str(e)
                print(f"[Search Tool] DuckDuckGo {method_name} attempt {attempt+1} failed: {err_str}")
                exceptions.append(f"DDG {method_name} (attempt {attempt+1}): {err_str}")
                time.sleep(1.0)
                
    err_summary = "; ".join(set(exceptions))
    return f"Search failed to retrieve results. Technical errors: {err_summary}. Please rely on your pre-ingested knowledge base or notify the user of the web search rate limit."
