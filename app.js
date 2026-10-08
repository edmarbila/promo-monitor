(() => {
  "use strict";

  const cfg = window.APP_CONFIG || {};
  const missing = ["SUPABASE_URL","SUPABASE_PUBLISHABLE_KEY","CONTROL_API_URL"]
    .filter(k => !cfg[k] || String(cfg[k]).includes("SEU-"));
  if (missing.length) {
    document.body.innerHTML = `<div style="padding:24px;font-family:sans-serif">
      Configure <b>config.js</b>: ${missing.join(", ")}</div>`;
    return;
  }

  const db = supabase.createClient(cfg.SUPABASE_URL, cfg.SUPABASE_PUBLISHABLE_KEY, {
    auth: { persistSession:true, autoRefreshToken:true, detectSessionInUrl:true }
  });
  const $ = id => document.getElementById(id);
  const recoveryRedirectUrl = `${window.location.origin}${window.location.pathname}`;
  let passwordRecoveryMode = false;

  const state = {
    session:null,user:null,keywords:[],groups:[],requests:[],occurrences:[],
    coupons:[],stores:[],worker:null,telegram:null,view:"dashboard"
  };

  function notify(msg,type=""){
    const el=$("toast"); el.textContent=msg; el.className=`toast ${type}`.trim(); el.hidden=false;
    clearTimeout(notify.timer); notify.timer=setTimeout(()=>el.hidden=true,3500);
  }
  function fail(err){ console.error(err); notify(err?.message || err?.detail || String(err),"error"); }
  function clear(el){ while(el.firstChild) el.removeChild(el.firstChild); el.classList.remove("empty"); }
  function empty(el,msg){ clear(el); el.classList.add("empty"); el.textContent=msg; }
  function fmt(v){
    if(!v) return "—";
    const d=new Date(v); if(Number.isNaN(d.getTime())) return String(v);
    return new Intl.DateTimeFormat("pt-BR",{dateStyle:"short",timeStyle:"short"}).format(d);
  }
  function btn(text,cls,fn){
    const b=document.createElement("button"); b.type="button"; b.textContent=text; b.className=cls; b.addEventListener("click",fn); return b;
  }
  function slugify(v){
    return v.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase()
      .replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
  }

  async function api(path,opts={}){
    const token=state.session?.access_token;
    if(!token) throw new Error("Sessão expirada.");
    const r=await fetch(`${cfg.CONTROL_API_URL}${path}`,{
      ...opts,
      headers:{
        "Content-Type":"application/json",
        "Authorization":`Bearer ${token}`,
        ...(opts.headers||{})
      }
    });
    const data=await r.json().catch(()=>({}));
    if(!r.ok) throw new Error(data.detail || `Erro HTTP ${r.status}`);
    return data;
  }

  function setAuthMode(mode){
    const login=mode==="login";
    const signup=mode==="signup";
    const recovery=mode==="recovery";
    const reset=mode==="reset";
    $("loginForm").hidden=!login;
    $("signupForm").hidden=!signup;
    $("recoveryForm").hidden=!recovery;
    $("resetPasswordForm").hidden=!reset;
    $("authTabs").hidden=recovery||reset;
    $("tabLogin").classList.toggle("active",login);
    $("tabSignup").classList.toggle("active",signup);
    $("authMessage").hidden=true;
  }
  $("tabLogin").onclick=()=>setAuthMode("login");
  $("tabSignup").onclick=()=>setAuthMode("signup");
  $("forgotPasswordBtn").onclick=()=>{
    $("recoveryEmail").value=$("loginEmail").value.trim();
    setAuthMode("recovery");
  };
  $("backToLoginBtn").onclick=()=>setAuthMode("login");

  $("loginForm").addEventListener("submit",async e=>{
    e.preventDefault();
    const {data,error}=await db.auth.signInWithPassword({
      email:$("loginEmail").value.trim(), password:$("loginPassword").value
    });
    if(error) return fail(error);
    await setSession(data.session);
  });

  $("recoveryForm").addEventListener("submit",async e=>{
    e.preventDefault();
    const email=$("recoveryEmail").value.trim();
    const {error}=await db.auth.resetPasswordForEmail(email,{redirectTo:recoveryRedirectUrl});
    if(error) return fail(error);
    const m=$("authMessage");
    m.hidden=false;
    m.textContent="Se o e-mail estiver cadastrado, você receberá um link para criar uma nova senha.";
  });

  $("resetPasswordForm").addEventListener("submit",async e=>{
    e.preventDefault();
    const password=$("resetPassword").value;
    const confirmPassword=$("resetPasswordConfirm").value;
    if(password!==confirmPassword) return notify("As senhas não coincidem.","error");
    const {error}=await db.auth.updateUser({password});
    if(error) return fail(error);
    passwordRecoveryMode=false;
    $("resetPassword").value="";
    $("resetPasswordConfirm").value="";
    history.replaceState({},document.title,window.location.pathname);
    await db.auth.signOut();
    await setSession(null);
    setAuthMode("login");
    notify("Senha alterada. Entre novamente com a nova senha.","success");
  });

  $("signupForm").addEventListener("submit",async e=>{
    e.preventDefault();
    const {data,error}=await db.auth.signUp({
      email:$("signupEmail").value.trim(),
      password:$("signupPassword").value,
      options:{data:{display_name:$("signupName").value.trim()}}
    });
    if(error) return fail(error);
    const m=$("authMessage"); m.hidden=false;
    m.textContent=data.session
      ? "Conta criada. Entrando..."
      : "Conta criada. Confirme seu e-mail e depois faça login.";
    if(data.session) await setSession(data.session);
  });

  $("logoutBtn").onclick=async()=>{ await db.auth.signOut(); await setSession(null); };

  $("changePasswordForm").addEventListener("submit",async e=>{
    e.preventDefault();
    const password=$("changePassword").value;
    const confirmPassword=$("changePasswordConfirm").value;
    if(password!==confirmPassword) return notify("As senhas não coincidem.","error");
    const {error}=await db.auth.updateUser({password});
    if(error) return fail(error);
    $("changePassword").value="";
    $("changePasswordConfirm").value="";
    notify("Senha alterada no Supabase com sucesso.","success");
  });

  async function setSession(session){
    state.session=session; state.user=session?.user||null;
    if(passwordRecoveryMode){
      $("authView").hidden=false;
      $("appView").hidden=true;
      setAuthMode("reset");
      return;
    }
    $("authView").hidden=!!state.user; $("appView").hidden=!state.user;
    if(!state.user) return;
    $("userEmail").textContent=state.user.email||"";
    $("accountEmail").textContent=state.user.email||"—";
    await loadAll();
  }

  async function loadKeywords(){
    const {data,error}=await db.from("tg_keywords").select("*").order("word");
    if(error) throw error; state.keywords=data||[]; renderKeywords();
  }
  async function loadGroups(){
    const [g,r]=await Promise.all([
      db.from("tg_groups").select("*").order("name"),
      db.from("tg_group_requests").select("*").order("id",{ascending:false}).limit(20)
    ]);
    if(g.error) throw g.error; if(r.error) throw r.error;
    state.groups=g.data||[]; state.requests=r.data||[]; renderGroups(); renderRequests();
  }
  async function loadOccurrences(){
    const {data,error}=await db.from("tg_occurrences").select("*")
      .order("occurred_at",{ascending:false}).limit(300);
    if(error) throw error; state.occurrences=data||[]; renderHistory(); renderRecent();
  }
  async function loadCoupons(){
    const {data,error}=await db.from("tg_coupons").select("*").eq("active",true)
      .order("last_seen_at",{ascending:false}).limit(400);
    if(error) throw error;
    state.coupons=(data||[]).filter(x=>x.source==="telegram" || String(x.code||"").trim());
    renderCoupons(); renderRecentCoupons();
  }
  async function loadStores(){
    const {data,error}=await db.from("tg_coupon_sites").select("*").order("store_name");
    if(error) throw error; state.stores=data||[]; renderStores();
  }
  async function loadWorker(){
    const {data,error}=await db.from("tg_worker_status").select("*")
      .eq("user_id",state.user.id).maybeSingle();
    if(error) throw error; state.worker=data||null; renderWorker();
  }
  async function loadTelegram(){
    try{ state.telegram=await api("/telegram/status"); }
    catch(e){ state.telegram={status:"error",last_error:e.message}; }
    renderTelegram();
  }
  async function loadAll(){
    await Promise.all([
      loadKeywords(),loadGroups(),loadOccurrences(),loadCoupons(),
      loadStores(),loadWorker(),loadTelegram()
    ]);
    renderCounts();
  }
  function renderCounts(){
    $("countGroups").textContent=state.groups.filter(x=>x.active).length;
    $("countKeywords").textContent=state.keywords.filter(x=>x.active).length;
    $("countOccurrences").textContent=state.occurrences.length;
    $("countCoupons").textContent=state.coupons.length;
  }
  function renderWorker(){
    const w=state.worker;
    const online=!!(w?.last_heartbeat && Date.now()-new Date(w.last_heartbeat).getTime()<90000 && w.state==="online");
    const el=$("workerBadge"); el.className=`badge ${online?"online":"offline"}`;
    el.querySelector("span").textContent=online?"Worker online":"Worker offline";
  }

  function renderKeywords(){
    const host=$("keywordsList"); clear(host);
    if(!state.keywords.length) return empty(host,"Nenhuma palavra cadastrada.");
    for(const x of state.keywords){
      const row=document.createElement("div"); row.className="item";
      const main=document.createElement("div");
      const s=document.createElement("strong"); s.textContent=x.word;
      const sub=document.createElement("span"); sub.textContent=x.active?"Ativa":"Desativada";
      main.append(s,sub);
      const actions=document.createElement("div"); actions.className="actions";
      actions.append(
        btn(x.active?"Desativar":"Ativar",`btn mini ${x.active?"active-btn":"inactive-btn"}`,async()=>{
          try{ const {error}=await db.from("tg_keywords").update({active:!x.active}).eq("id",x.id); if(error)throw error; await loadKeywords(); renderCounts(); }catch(e){fail(e);}
        }),
        btn("Excluir","btn mini danger",async()=>{
          if(!confirm(`Excluir "${x.word}"?`))return;
          try{ const {error}=await db.from("tg_keywords").delete().eq("id",x.id); if(error)throw error; await loadKeywords(); renderCounts(); }catch(e){fail(e);}
        })
      );
      row.append(main,actions); host.append(row);
    }
  }
  $("keywordForm").addEventListener("submit",async e=>{
    e.preventDefault();
    try{
      const word=$("keywordInput").value.trim(); if(!word)return;
      const existing=state.keywords.find(x=>String(x.word||"").trim().toLocaleLowerCase("pt-BR")===word.toLocaleLowerCase("pt-BR"));
      if(existing){
        notify(`A palavra "${existing.word}" já está cadastrada. A busca não diferencia maiúsculas de minúsculas.`,"error");
        return;
      }
      const {error}=await db.from("tg_keywords").insert({user_id:state.user.id,word,active:true});
      if(error){
        if(String(error.code||"")==="23505"){
          notify("Essa palavra já está cadastrada. A busca considera BUG, Bug e bug como a mesma palavra.","error");
          return;
        }
        throw error;
      }
      $("keywordInput").value=""; await loadKeywords(); renderCounts(); notify("Palavra adicionada.","success");
    }catch(e2){fail(e2);}
  });

  function renderGroups(){
    const host=$("groupsList"); clear(host);
    if(!state.groups.length) return empty(host,"Nenhum grupo configurado.");
    for(const x of state.groups){
      const row=document.createElement("div"); row.className="item";
      const main=document.createElement("div");
      const s=document.createElement("strong"); s.textContent=x.name||x.username||String(x.telegram_group_id);
      const sub=document.createElement("span"); sub.textContent=`${x.username?"@"+x.username:"privado"} • ${x.telegram_group_id} • ${x.active?"ativo":"desativado"}`;
      main.append(s,sub);
      const actions=document.createElement("div"); actions.className="actions";
      actions.append(
        btn(x.active?"Desativar":"Ativar",`btn mini ${x.active?"active-btn":"inactive-btn"}`,async()=>{
          try{const {error}=await db.from("tg_groups").update({active:!x.active}).eq("id",x.id);if(error)throw error;await loadGroups();renderCounts();}catch(e){fail(e);}
        }),
        btn("Excluir","btn mini danger",async()=>{
          if(!confirm("Remover este grupo?"))return;
          try{const {error}=await db.from("tg_groups").delete().eq("id",x.id);if(error)throw error;await loadGroups();renderCounts();}catch(e){fail(e);}
        })
      );
      row.append(main,actions); host.append(row);
    }
  }
  $("groupForm").addEventListener("submit",async e=>{
    e.preventDefault();
    try{
      const identifier=$("groupIdentifier").value.trim();
      const {error}=await db.from("tg_group_requests").insert({user_id:state.user.id,identifier,status:"pending"});
      if(error)throw error; $("groupIdentifier").value=""; await loadGroups(); notify("Grupo enviado para validação.","success");
    }catch(e2){fail(e2);}
  });
  function renderRequests(){
    const host=$("requestsList"); clear(host);
    for(const x of state.requests.slice(0,8)){
      const row=document.createElement("div"); row.className=`request ${x.status}`;
      row.textContent=`${x.identifier} — ${x.status}${x.error_message?": "+x.error_message:""}`; host.append(row);
    }
  }

  function occurrenceCard(x){
    const card=document.createElement("article"); card.className="occurrence";
    const top=document.createElement("div"); top.className="occurrence-top";
    const left=document.createElement("div");
    const s=document.createElement("strong"); s.textContent=x.group_name||"Grupo";
    const meta=document.createElement("div"); meta.className="meta"; meta.textContent=`${x.sender||"Desconhecido"} • ${fmt(x.occurred_at)}`;
    left.append(s,meta);
    const tag=document.createElement("span"); tag.className="tag"; tag.textContent=x.keyword||"match";
    top.append(left,tag);
    const msg=document.createElement("p"); msg.className="message"; msg.textContent=x.message||"";
    card.append(top,msg);
    if(x.message_link){
      const a=document.createElement("a"); a.className="link"; a.href=x.message_link; a.target="_blank"; a.rel="noopener"; a.textContent="Abrir mensagem"; card.append(a);
    }
    return card;
  }
  function renderHistory(){
    const host=$("historyList"); clear(host);
    const q=$("historySearch").value.trim().toLocaleLowerCase("pt-BR");
    const rows=state.occurrences.filter(x=>!q || [x.group_name,x.sender,x.keyword,x.message].filter(Boolean).join(" ").toLocaleLowerCase("pt-BR").includes(q));
    if(!rows.length)return empty(host,"Nenhuma ocorrência nas últimas 24 horas.");
    rows.forEach(x=>host.append(occurrenceCard(x)));
  }
  function renderRecent(){
    const host=$("recentOccurrences"); clear(host);
    const rows=state.occurrences.slice(0,8);
    if(!rows.length)return empty(host,"Nenhuma ocorrência nas últimas 24 horas.");
    rows.forEach(x=>host.append(occurrenceCard(x)));
  }
  $("historySearch").addEventListener("input",renderHistory);

  function couponCard(x){
    const card=document.createElement("article"); card.className="coupon";
    const top=document.createElement("div"); top.className="coupon-top";
    const left=document.createElement("div");
    const s=document.createElement("strong"); s.textContent=x.store_name||"Cupom";
    const meta=document.createElement("div"); meta.className="meta"; meta.textContent=`${x.discount_text||"oferta"} • ${fmt(x.last_seen_at)}`;
    left.append(s,meta);
    const tag=document.createElement("span"); tag.className="tag";
    tag.textContent=({meliuz:"Méliuz",cuponeria:"Cuponeria",picodi:"Picodi",promobit:"Promobit",telegram:"Telegram",manual:"Manual"})[x.source]||x.source;
    top.append(left,tag);
    const title=document.createElement("p"); title.className="coupon-title";
    title.textContent=x.title||(`Cupom ${x.store_name||""}`.trim());
    card.append(top,title);
    if(x.details){
      const details=document.createElement("p");
      details.className="coupon-details";
      details.textContent=x.details;
      card.append(details);
    }
    if(x.code){
      const c=document.createElement("div");c.className="code";
      const label=document.createElement("span");label.textContent="Código";
      const value=document.createElement("strong");value.textContent=x.code;
      c.append(label,value);card.append(c);
    }
    const actions=document.createElement("div"); actions.className="actions";
    if(x.code) actions.append(btn("Copiar","btn mini secondary",()=>{navigator.clipboard?.writeText(x.code);notify("Código copiado.","success");}));
    if(x.source_url){const a=document.createElement("a");a.className="btn mini secondary link";a.href=x.source_url;a.target="_blank";a.rel="noopener";a.textContent="Abrir fonte";actions.append(a);}
    if(actions.childNodes.length)card.append(actions);
    return card;
  }
  function filteredCoupons(){
    const q=$("couponSearch").value.trim().toLocaleLowerCase("pt-BR"), source=$("couponSource").value;
    return state.coupons.filter(x=>{
      if(source && x.source!==source)return false;
      if(!q)return true;
      return [x.store_name,x.title,x.code,x.discount_text,x.details].filter(Boolean).join(" ").toLocaleLowerCase("pt-BR").includes(q);
    });
  }
  function renderCoupons(){
    const host=$("couponsList"); clear(host); const rows=filteredCoupons();
    if(!rows.length)return empty(host,"Nenhum cupom ativo encontrado.");
    rows.forEach(x=>host.append(couponCard(x)));
  }
  function renderRecentCoupons(){
    const host=$("recentCoupons"); clear(host); const rows=state.coupons.slice(0,6);
    if(!rows.length)return empty(host,"Nenhum cupom encontrado ainda.");
    rows.forEach(x=>host.append(couponCard(x)));
  }
  $("couponSearch").addEventListener("input",renderCoupons);
  $("couponSource").addEventListener("change",renderCoupons);

  $("storeForm").addEventListener("submit",async e=>{
    e.preventDefault();
    try{
      const name=$("storeName").value.trim(); const sources=[];
      if($("sourceMeliuz").checked)sources.push("meliuz");
      if($("sourceCuponeria").checked)sources.push("cuponeria");
      if($("sourcePicodi").checked)sources.push("picodi");
      if($("sourcePromobit").checked)sources.push("promobit");
      if(!sources.length)throw new Error("Selecione pelo menos uma fonte.");
      const slug=slugify(name);
      const {data,error}=await db.from("tg_coupon_sites")
        .insert({user_id:state.user.id,store_name:name,store_slug:slug,sources,active:true})
        .select("id").single();
      if(error)throw error;
      $("storeName").value="";
      await loadStores();
      notify("Loja cadastrada. Buscando cupons agora...","success");
      try{
        const scan=await api("/coupons/scan",{method:"POST",body:JSON.stringify({store_id:data.id})});
        await loadCoupons(); renderCounts();
        if(scan.total>0){
          notify(`${scan.total} código(s) de cupom encontrado(s) para ${name}.`,"success");
        }else{
          notify(`Busca concluída para ${name}. Nenhum código digitável ativo foi encontrado nas fontes agora.`);
        }
      }catch(scanError){
        console.error(scanError);
        notify("Loja cadastrada, mas a busca imediata falhou. O worker tentará novamente no próximo ciclo.","error");
      }
    }catch(e2){fail(e2);}
  });
  function renderStores(){
    const host=$("storesList"); clear(host);
    if(!state.stores.length)return empty(host,"Nenhuma loja cadastrada.");
    for(const x of state.stores){
      const row=document.createElement("div");row.className="item";
      const main=document.createElement("div");const s=document.createElement("strong");s.textContent=x.store_name;
      const sub=document.createElement("span");sub.textContent=`${x.store_slug} • ${(x.sources||[]).join(" + ")} • ${x.active?"ativa":"pausada"}`;main.append(s,sub);
      const actions=document.createElement("div");actions.className="actions";
      actions.append(
        btn("Buscar agora","btn mini secondary",async()=>{
          try{
            notify(`Buscando cupons de ${x.store_name}...`);
            const scan=await api("/coupons/scan",{method:"POST",body:JSON.stringify({store_id:x.id})});
            await loadCoupons(); renderCounts();
            notify(scan.total>0
              ? `${scan.total} código(s) encontrado(s) para ${x.store_name}.`
              : `Nenhum código digitável ativo encontrado agora para ${x.store_name}.`,
              scan.total>0?"success":"");
          }catch(e){fail(e);}
        }),
        btn(x.active?"Pausar":"Ativar",`btn mini ${x.active?"active-btn":"inactive-btn"}`,async()=>{
          try{const {error}=await db.from("tg_coupon_sites").update({active:!x.active}).eq("id",x.id);if(error)throw error;await loadStores();}catch(e){fail(e);}
        }),
        btn("Excluir","btn mini danger",async()=>{
          if(!confirm("Excluir esta loja?"))return;
          try{const {error}=await db.from("tg_coupon_sites").delete().eq("id",x.id);if(error)throw error;await loadStores();}catch(e){fail(e);}
        })
      );
      row.append(main,actions);host.append(row);
    }
  }

  function maybeShowTelegramSetupPrompt(){
    if(!state.user || state.telegram?.status!=="not_configured") return;
    const key=`promo-monitor:telegram-setup:${state.user.id}`;
    if(sessionStorage.getItem(key)==="1") return;
    $("telegramSetupModal").hidden=false;
  }

  function closeTelegramSetupPrompt(){
    if(state.user){
      sessionStorage.setItem(`promo-monitor:telegram-setup:${state.user.id}`,"1");
    }
    $("telegramSetupModal").hidden=true;
  }

  $("telegramSetupGoBtn").onclick=()=>{
    closeTelegramSetupPrompt();
    switchView("telegram");
  };
  $("telegramSetupLaterBtn").onclick=closeTelegramSetupPrompt;

  function renderTelegram(){
    const s=state.telegram?.status||"not_configured";
    const names={not_configured:"Não configurado",code_sent:"Código enviado","2fa_required":"2FA necessário",connected:"Conectado",error:"Erro",disconnected:"Desconectado"};
    $("telegramStatusText").textContent=s==="connected"
      ? `Conta conectada${state.telegram?.phone_hint?` (${state.telegram.phone_hint})`:""}.`
      : state.telegram?.last_error || names[s] || s;
    $("telegramPill").textContent=names[s]||s;
    $("telegramCredentialsForm").hidden=["code_sent","2fa_required","connected"].includes(s);
    $("telegramCodeForm").hidden=s!=="code_sent";
    $("telegram2faForm").hidden=s!=="2fa_required";
    $("disconnectTelegramBtn").hidden=s!=="connected";
    $("telegramBanner").hidden=s==="connected";
    if(s==="connected"){
      $("telegramSetupModal").hidden=true;
    }else{
      maybeShowTelegramSetupPrompt();
    }
  }

  $("telegramCredentialsForm").addEventListener("submit",async e=>{
    e.preventDefault();
    try{
      await api("/telegram/request-code",{method:"POST",body:JSON.stringify({
        api_id:Number($("tgApiId").value),
        api_hash:$("tgApiHash").value.trim(),
        phone:$("tgPhone").value.trim()
      })});
      await loadTelegram(); notify("Código enviado pelo Telegram.","success");
    }catch(e2){fail(e2);}
  });
  $("telegramCodeForm").addEventListener("submit",async e=>{
    e.preventDefault();
    try{
      const r=await api("/telegram/confirm-code",{method:"POST",body:JSON.stringify({code:$("tgCode").value.trim()})});
      await loadTelegram(); await loadWorker();
      notify(r.status==="connected"?"Telegram conectado.":"Informe sua senha 2FA.","success");
    }catch(e2){fail(e2);}
  });
  $("telegram2faForm").addEventListener("submit",async e=>{
    e.preventDefault();
    try{
      await api("/telegram/confirm-2fa",{method:"POST",body:JSON.stringify({password:$("tg2fa").value})});
      $("tg2fa").value=""; await loadTelegram(); await loadWorker(); notify("Telegram conectado.","success");
    }catch(e2){fail(e2);}
  });
  $("disconnectTelegramBtn").onclick=async()=>{
    if(!confirm("Desconectar sua conta Telegram deste monitor?"))return;
    try{await api("/telegram/disconnect",{method:"POST"});await loadTelegram();await loadWorker();}catch(e){fail(e);}
  };

  function switchView(name){
    state.view=name;
    document.querySelectorAll(".view").forEach(x=>x.classList.remove("active"));
    $(`view-${name}`)?.classList.add("active");
    document.querySelectorAll(".nav[data-view]").forEach(x=>x.classList.toggle("active",x.dataset.view===name));
    const titles={dashboard:"Dashboard",keywords:"Palavras-chave",groups:"Grupos",coupons:"Cupons",stores:"Lojas de interesse",history:"Histórico 24h",telegram:"Configuração do Telegram",account:"Minha conta",project:"Projeto"};
    $("pageTitle").textContent=titles[name]||"Promo Monitor";
    refresh(name).catch(fail);
  }
  async function refresh(name){
    if(name==="dashboard")await Promise.all([loadOccurrences(),loadCoupons(),loadWorker()]);
    if(name==="keywords")await loadKeywords();
    if(name==="groups")await loadGroups();
    if(name==="coupons")await loadCoupons();
    if(name==="stores")await loadStores();
    if(name==="history")await loadOccurrences();
    if(name==="telegram")await Promise.all([loadTelegram(),loadWorker()]);
    renderCounts();
  }
  document.querySelectorAll(".nav[data-view]").forEach(x=>x.onclick=()=>switchView(x.dataset.view));
  document.querySelectorAll("[data-jump]").forEach(x=>x.onclick=()=>switchView(x.dataset.jump));

  db.auth.onAuthStateChange((event,session)=>{
    if(event==="PASSWORD_RECOVERY"){
      passwordRecoveryMode=true;
      return setSession(session).catch(fail);
    }
    setSession(session).catch(fail);
  });
  db.auth.getSession().then(({data})=>setSession(data.session).catch(fail));

  setInterval(()=>{
    if(!state.user)return;
    loadWorker().catch(()=>{}); loadTelegram().catch(()=>{});
    if(state.view==="coupons")loadCoupons().catch(()=>{});
  },15000);
})();
