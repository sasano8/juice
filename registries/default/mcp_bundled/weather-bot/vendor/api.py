"""会話 API（OpenAI 互換）＋ 簡易チャット UI（自動生成）。

- POST /v1/chat/completions : LangGraph グラフに会話を渡して応答（OpenAI 互換）。
- GET  /chat                : ローカル完結の簡易チャット画面（/v1/chat/completions を叩く）。
  ※ `/ui` は langgraph dev（Studio）が使うため避け、`/chat` に置いて衝突を回避。
- GET  /                    : /chat へリダイレクト。
"""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from graph import CONFIG, make_graph, resolve_api_key

app = FastAPI()
_agent = None


async def _get_agent():
    global _agent
    if _agent is None:
        _agent = await make_graph()
    return _agent


CHAT_HTML = """
<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>__NAME__ — chat</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem}
 #log{border:1px solid #ddd;border-radius:8px;padding:1rem;height:60vh;overflow:auto;background:#fafafa}
 .msg{margin:.6rem 0;white-space:pre-wrap}
 .u{color:#0a7}.a{color:#222}
 form{display:flex;gap:.5rem;margin-top:.6rem}
 input{flex:1;padding:.6rem;border:1px solid #ccc;border-radius:6px}
 button{padding:.6rem 1rem;border:0;border-radius:6px;background:#0a7;color:#fff;cursor:pointer}
</style></head><body>
<h2>__NAME__</h2>
<div id="log"></div>
<form id="f"><input id="t" placeholder="メッセージを入力…" autocomplete="off" autofocus><button>送信</button></form>
<script>
const log=document.getElementById("log"),f=document.getElementById("f"),t=document.getElementById("t");
const messages=[];
function add(role,text){const d=document.createElement("div");d.className="msg "+(role==="user"?"u":"a");d.textContent=(role==="user"?"あなた: ":"AI: ")+text;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
f.onsubmit=async(e)=>{e.preventDefault();const text=t.value.trim();if(!text)return;t.value="";
 add("user",text);messages.push({role:"user",content:text});
 const ph=add("assistant","…");
 try{
  const r=await fetch("/v1/chat/completions",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({messages})});
  const raw=await r.text();
  let data=null; try{data=JSON.parse(raw);}catch(_){}
  if(!r.ok){
   const msg=(data&&data.error&&data.error.message)||raw||("HTTP "+r.status);
   ph.textContent="⚠️ エラー: "+msg; messages.pop(); return;
  }
  const reply=(((data&&data.choices||[])[0]||{}).message||{}).content;
  if(reply==null){ph.textContent="⚠️ エラー: 想定外の応答 "+raw; messages.pop(); return;}
  ph.textContent="AI: "+reply;messages.push({role:"assistant",content:reply});
 }catch(err){ph.textContent="⚠️ エラー: "+err; messages.pop();}
};
</script></body></html>
"""


@app.get("/")
def root():
    return RedirectResponse("/chat")


@app.get("/chat", response_class=HTMLResponse)
@app.get("/chat/", response_class=HTMLResponse, include_in_schema=False)
def chat_ui():
    return CHAT_HTML.replace("__NAME__", CONFIG.get("name", "chat"))


@app.post("/v1/chat/completions")
async def chat_completions(body: dict):
    # 原因を分かりやすく返す: キー未設定は 400、それ以外の失敗は 502（どちらも JSON）。
    if not resolve_api_key():
        env = CONFIG.get("api_key_env") or "ANTHROPIC_API_KEY"
        return JSONResponse(
            status_code=400,
            content={"error": {
                "type": "missing_api_key",
                "message": f"API キーが未設定です。環境変数 {env}（または api_key_file）を設定して起動してください。",
            }},
        )
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in body.get("messages", [])
        if m.get("role") in ("system", "user", "assistant")
    ]
    try:
        agent = await _get_agent()
        result = await agent.ainvoke({"messages": messages})
        text = result["messages"][-1].content
        if isinstance(text, list):  # content blocks の場合は text を連結
            text = "".join(b.get("text", "") for b in text if isinstance(b, dict))
    except Exception as e:  # noqa: BLE001  LLM/接続エラー等を JSON で返す
        return JSONResponse(
            status_code=502,
            content={"error": {"type": type(e).__name__, "message": str(e)}},
        )
    return {
        "id": f"chatcmpl-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "model": CONFIG["model"],
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
    }
