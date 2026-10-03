import os, sqlite3, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
URL=os.environ.get("SUPABASE_URL","").strip()
KEY=os.environ.get("SUPABASE_SERVICE_ROLE_KEY","").strip()
OWNER=os.environ.get("OWNER_USER_ID","").strip()
if not all([URL,KEY,OWNER]):
    raise RuntimeError("Defina SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY e OWNER_USER_ID.")

db=create_client(URL,KEY)
tz=ZoneInfo("America/Sao_Paulo")

def parse_date(v):
    if not v:return datetime.now(tz).isoformat()
    for f in ("%d/%m/%Y %H:%M:%S","%Y-%m-%d %H:%M:%S"):
        try:return datetime.strptime(v,f).replace(tzinfo=tz).isoformat()
        except ValueError:pass
    return datetime.now(tz).isoformat()

def main(path):
    p=Path(path)
    if not p.exists():raise FileNotFoundError(p)
    c=sqlite3.connect(p);c.row_factory=sqlite3.Row

    groups=c.execute("select * from groups").fetchall()
    for r in groups:
        db.table("tg_groups").upsert({"user_id":OWNER,"telegram_group_id":int(r["id"]),"name":r["name"] or "","username":r["username"] or "","active":bool(r["active"])},on_conflict="user_id,telegram_group_id").execute()
    print("Grupos:",len(groups))

    kws=c.execute("select * from keywords").fetchall()
    existing=db.table("tg_keywords").select("word").eq("user_id",OWNER).execute().data or []
    seen={x["word"].strip().casefold() for x in existing}
    n=0
    for r in kws:
        w=(r["word"] or "").strip()
        if not w or w.casefold() in seen:continue
        db.table("tg_keywords").insert({"user_id":OWNER,"word":w,"active":bool(r["active"])}).execute();seen.add(w.casefold());n+=1
    print("Palavras novas:",n)

    occ=c.execute("select * from occurrences").fetchall()
    for r in occ:
        db.table("tg_occurrences").upsert({"user_id":OWNER,"occurred_at":parse_date(r["date"]),"telegram_group_id":r["group_id"],"group_name":r["group_name"] or "","username":r["username"] or "","sender":r["sender"] or "","keyword":r["keyword"] or "","message":r["message"] or "","message_id":r["message_id"],"message_link":r["message_link"] or ""},on_conflict="user_id,telegram_group_id,message_id,keyword").execute()
    print("Ocorrências:",len(occ))

if __name__=="__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "telegram_monitor.db")
