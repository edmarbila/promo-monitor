import os
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

URL = os.environ.get("SUPABASE_URL","").strip()
KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY","").strip()
WEB_PANEL_URL = os.environ.get("WEB_PANEL_URL","http://localhost:8080").strip()

BG="#06101d"; PANEL="#0d1929"; PANEL2="#13233a"; TEXT="#f6f9fd"
MUTED="#9eb2ca"; PRIMARY="#329dff"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Promo Monitor")
        self.geometry("1180x760")
        self.minsize(900,620)
        self.configure(bg=BG)
        self.db=create_client(URL,KEY)
        self.user=None
        self.style_ui()
        self.login_screen()

    def style_ui(self):
        s=ttk.Style(self)
        try:s.theme_use("clam")
        except:pass
        s.configure("TFrame",background=BG)
        s.configure("TLabel",background=BG,foreground=TEXT,font=("Segoe UI",10))
        s.configure("Muted.TLabel",background=BG,foreground=MUTED,font=("Segoe UI",9))
        s.configure("Title.TLabel",background=BG,foreground=TEXT,font=("Segoe UI",23,"bold"))
        s.configure("TButton",padding=(12,9),font=("Segoe UI",9,"bold"))
        s.configure("Primary.TButton",background=PRIMARY,foreground="white")
        s.map("Primary.TButton",background=[("active","#167bd4")])
        s.configure("Treeview",background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=30)
        s.configure("Treeview.Heading",background=PANEL2,foreground=TEXT,font=("Segoe UI",9,"bold"))
        s.configure("TNotebook",background=BG,borderwidth=0)
        s.configure("TNotebook.Tab",background=PANEL2,foreground=MUTED,padding=(14,9))
        s.map("TNotebook.Tab",background=[("selected",PRIMARY)],foreground=[("selected","white")])

    def wipe(self):
        for w in self.winfo_children():w.destroy()

    def login_screen(self):
        self.wipe()
        f=ttk.Frame(self,padding=40);f.place(relx=.5,rely=.5,anchor="center")
        ttk.Label(f,text="Promo Monitor",style="Title.TLabel").pack(anchor="w")
        ttk.Label(f,text="Painel Windows sincronizado com o painel web.",style="Muted.TLabel").pack(anchor="w",pady=(4,22))
        ttk.Label(f,text="E-mail").pack(anchor="w")
        email=ttk.Entry(f,width=42);email.pack(fill="x",pady=(4,12))
        ttk.Label(f,text="Senha").pack(anchor="w")
        password=ttk.Entry(f,width=42,show="*");password.pack(fill="x",pady=(4,18))

        def enter():
            try:
                result=self.db.auth.sign_in_with_password({"email":email.get().strip(),"password":password.get()})
                self.user=result.user;self.app_screen()
            except Exception as exc:messagebox.showerror("Login",str(exc))
        ttk.Button(f,text="Entrar",style="Primary.TButton",command=enter).pack(fill="x")

    def app_screen(self):
        self.wipe()
        out=ttk.Frame(self,padding=18);out.pack(fill="both",expand=True)
        head=ttk.Frame(out);head.pack(fill="x",pady=(0,14))
        ttk.Label(head,text="Promo Monitor",style="Title.TLabel").pack(side="left")
        ttk.Label(head,text=self.user.email or "",style="Muted.TLabel").pack(side="right")

        nb=ttk.Notebook(out);nb.pack(fill="both",expand=True)
        self.tabs={}
        for key,title in [("dash","Dashboard"),("keywords","Palavras"),("groups","Grupos"),("coupons","Cupons"),("history","Histórico 24h"),("telegram","Telegram")]:
            t=ttk.Frame(nb,padding=14);nb.add(t,text=title);self.tabs[key]=t
        self.build_dash();self.build_keywords();self.build_groups();self.build_coupons();self.build_history();self.build_telegram()

    def build_dash(self):
        t=self.tabs["dash"]
        ttk.Label(t,text="Resumo",style="Title.TLabel").pack(anchor="w",pady=(0,12))
        self.summary=tk.Text(t,bg=PANEL,fg=TEXT,relief="flat",font=("Consolas",11),height=15)
        self.summary.pack(fill="both",expand=True)
        ttk.Button(t,text="Atualizar",command=self.refresh_dash).pack(anchor="w",pady=10)
        self.refresh_dash()

    def refresh_dash(self):
        try:
            kw=self.db.table("tg_keywords").select("id",count="exact").eq("active",True).execute()
            gp=self.db.table("tg_groups").select("id",count="exact").eq("active",True).execute()
            oc=self.db.table("tg_occurrences").select("id",count="exact").execute()
            cp=self.db.table("tg_coupons").select("id",count="exact").eq("active",True).execute()
            self.summary.delete("1.0","end")
            self.summary.insert("1.0",f"Palavras ativas: {kw.count or 0}\nGrupos ativos:    {gp.count or 0}\nOcorrências 24h:  {oc.count or 0}\nCupons ativos:    {cp.count or 0}\n")
        except Exception as exc:messagebox.showerror("Dashboard",str(exc))

    def table_tab(self,key,columns,loader):
        t=self.tabs[key]
        tree=ttk.Treeview(t,columns=[c[0] for c in columns],show="headings")
        for col,title,width in columns:
            tree.heading(col,text=title);tree.column(col,width=width)
        tree.pack(fill="both",expand=True)
        def refresh():
            for i in tree.get_children():tree.delete(i)
            for row in loader():tree.insert("","end",values=row)
        ttk.Button(t,text="Atualizar",command=refresh).pack(anchor="w",pady=10)
        refresh()
        return tree,refresh

    def build_keywords(self):
        t=self.tabs["keywords"];top=ttk.Frame(t);top.pack(fill="x")
        entry=ttk.Entry(top);entry.pack(side="left",fill="x",expand=True,padx=(0,8))
        tree=ttk.Treeview(t,columns=("word","active"),show="headings")
        tree.heading("word",text="Palavra");tree.heading("active",text="Ativa")
        tree.pack(fill="both",expand=True,pady=12)
        def refresh():
            for i in tree.get_children():tree.delete(i)
            rows=self.db.table("tg_keywords").select("*").order("word").execute().data or []
            for r in rows:tree.insert("","end",iid=str(r["id"]),values=(r["word"],"Sim" if r["active"] else "Não"))
        def add():
            w=entry.get().strip()
            if not w:return
            self.db.table("tg_keywords").insert({"word":w,"active":True}).execute();entry.delete(0,"end");refresh()
        def toggle():
            s=tree.selection()
            if not s:return
            rid=int(s[0]);r=self.db.table("tg_keywords").select("active").eq("id",rid).single().execute().data
            self.db.table("tg_keywords").update({"active":not r["active"]}).eq("id",rid).execute();refresh()
        ttk.Button(top,text="Adicionar",style="Primary.TButton",command=add).pack(side="left")
        b=ttk.Frame(t);b.pack(fill="x")
        ttk.Button(b,text="Ativar / Desativar",command=toggle).pack(side="left")
        ttk.Button(b,text="Atualizar",command=refresh).pack(side="left",padx=8)
        refresh()

    def build_groups(self):
        t=self.tabs["groups"];top=ttk.Frame(t);top.pack(fill="x")
        entry=ttk.Entry(top);entry.pack(side="left",fill="x",expand=True,padx=(0,8))
        def request():
            v=entry.get().strip()
            if not v:return
            self.db.table("tg_group_requests").insert({"identifier":v}).execute();entry.delete(0,"end");messagebox.showinfo("Grupo","Pedido enviado ao worker.")
        ttk.Button(top,text="Adicionar grupo",style="Primary.TButton",command=request).pack(side="left")
        self.table_tab("groups",[("name","Grupo",300),("username","@username",180),("active","Ativo",80)],
            lambda:[(r["name"],r["username"],"Sim" if r["active"] else "Não") for r in (self.db.table("tg_groups").select("*").order("name").execute().data or [])])

    def build_coupons(self):
        self.table_tab("coupons",[("source","Fonte",90),("store","Loja",160),("discount","Desconto",120),("code","Código",130),("title","Descrição",500)],
            lambda:[(r["source"],r["store_name"],r.get("discount_text") or "",r.get("code") or "",r["title"]) for r in (self.db.table("tg_coupons").select("*").eq("active",True).order("last_seen_at",desc=True).limit(300).execute().data or [])])

    def build_history(self):
        self.table_tab("history",[("date","Data",170),("group","Grupo",180),("keyword","Palavra",120),("message","Mensagem",600)],
            lambda:[(r["occurred_at"],r["group_name"],r["keyword"],r["message"][:180]) for r in (self.db.table("tg_occurrences").select("*").order("occurred_at",desc=True).limit(300).execute().data or [])])

    def build_telegram(self):
        t=self.tabs["telegram"]
        ttk.Label(t,text="Configuração do Telegram",style="Title.TLabel").pack(anchor="w")
        ttk.Label(t,text="Por segurança, o login Telegram é feito no painel web. O API Hash e a sessão não ficam neste aplicativo.",style="Muted.TLabel",wraplength=700).pack(anchor="w",pady=(5,18))
        ttk.Button(t,text="Abrir configuração no painel web",style="Primary.TButton",command=lambda:webbrowser.open(WEB_PANEL_URL)).pack(anchor="w")

if __name__=="__main__":
    App().mainloop()
