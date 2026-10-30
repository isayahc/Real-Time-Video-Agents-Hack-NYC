// SPDX-License-Identifier: MPL-2.0
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const node = (tag, text) => { const n = document.createElement(tag); n.textContent = text; return n; };
  const money = n => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', minimumFractionDigits:3}).format(n);
  let config, task, record, busy = false;

  function error(text) { $('flow-error').textContent = text; $('flow-error').hidden = !text; }
  async function api(url, post = false) {
    const response = await fetch(url, post ? {method:'POST', headers:{'X-Workbench-Request':'1'}} : {});
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Request failed');
    return data;
  }
  function pause() { document.querySelectorAll('video').forEach(v => v.pause()); }
  function show(step) {
    pause();
    ['task-panel','change-panel','result-panel'].forEach((id,i) => $(id).hidden = i !== step);
    document.querySelectorAll('#journey button').forEach((b,i) => {
      if (i === step) b.setAttribute('aria-current','step'); else b.removeAttribute('aria-current');
    });
  }
  function media(id, url, poster) {
    const video = $(id);
    if (url) video.src = url; else video.removeAttribute('src');
    if (poster) video.setAttribute('poster',poster); else video.removeAttribute('poster');
    video.load();
  }
  function taskDetails() {
    $('task-title').textContent = task.label;
    $('task-description').textContent = task.description;
    $('task-timing').textContent = task.timing_source;
    $('task-requirements').textContent = 'Acceptance gates: ' + task.requirements;
    $('task-caption').textContent = task.human_caption;
    media('task-video',task.human_url,task.human_poster);
  }
  function selectTask() {
    pause(); error('');
    task = config.tasks.find(t => t.id === $('task-picker').value);
    record = null;
    history.replaceState(null,'',location.pathname);
    taskDetails(); candidates();
    $('flow-status').textContent = 'Pre-run demo: recorded human task and prepared 3D machine animations. Analyze researches and selects the approach.';
  }
  function link(url, title) {
    const a = node('a',title || url);
    try { const u = new URL(url); if (['http:','https:'].includes(u.protocol)) { a.href=u.href; a.target='_blank'; a.rel='noopener noreferrer'; } } catch {}
    return a;
  }
  function sources(host) {
    host.replaceChildren();
    if (!record?.research) { host.append(node('p',record?.error || 'Sources appear after the agent researches the task.')); return; }
    const research = record.research;
    host.append(node('p',research.note),node('p',`Retrieved ${new Date(research.queried_at*1000).toLocaleString()}`));
    research.results.forEach(r => host.append(link(r.url,r.title),node('p',r.content || '')));
  }
  function candidates() {
    const options = record?.alternatives || config.candidates[task.id] || [];
    $('recommendation').textContent = record?.agent_decision?.rationale || (record ? 'Historical saved analysis; no new agent decision.' : 'The agent will research this task and assess SO-101, Unitree G1 and custom tooling.');
    $('candidate-cards').replaceChildren();
    options.forEach(c => {
      const card = node('article',''); card.className='panel';
      card.append(node('h3',c.label + (record?.agent_decision && c.recommended ? ' · agent selected' : '')),
        node('p',record ? c.reason : 'Awaiting researched assessment.'));
      if (c.preview_url) {
        const video=document.createElement('video'); video.controls=true; video.playsInline=true;
        video.preload='none'; video.src=c.preview_url;
        if (c.preview_poster) video.poster=c.preview_poster;
        video.setAttribute('aria-label',c.label+' pre-run task animation');
        card.append(video,node('p','Pre-run 3D concept · authored motion, not capability evidence.'));
      }
      if (c.unresolved_gates) card.append(node('p','Unresolved: '+c.unresolved_gates.join('; ')));
      (c.source_urls || []).forEach((url,i) => card.append(link(url,`Source ${i+1} ↗ `)));
      $('candidate-cards').append(card);
    });
    $('estimate-preview').textContent = record?.agent_decision?.profile_rationale || '';
    $('view-comparison').hidden = !record?.estimate || record.status === 'failed';
    sources($('agent-sources'));
  }
  async function savedList() {
    const rows = await api('/api/fastening/runs');
    $('saved-analysis').replaceChildren(new Option('Choose an analysis',''));
    rows.forEach(r => $('saved-analysis').add(new Option(`${r.task_label || 'Fastening'} · ${r.profile} · ${new Date(r.created_at*1000).toLocaleString()}`,r.id)));
  }
  function breakdown(id, report) {
    $(id).replaceChildren();
    Object.entries(report.costs_usd_per_batch).forEach(([key,v]) => {
      if (!v.value) return;
      const row = node('div',''); row.className='breakdown';
      row.append(node('span',key.replaceAll('_',' ')),node('strong',money(v.value))); $(id).append(row);
    });
  }
  function render() {
    task = record.task || config.tasks[0];
    $('task-picker').value = task.id; taskDetails(); candidates();
    const r = record.estimate, c = record.intervention || {id:'custom',label:'Custom tooling'};
    $('result-title').textContent = `${task.label} · human versus ${c.label}`;
    $('scenario-name').textContent = r.profile_label + ' · illustrative estimates; acceptance unverified';
    media('human-result',task.human_url,task.human_poster);
    $('human-caption').textContent = task.human_caption;
    $('machine-title').textContent = c.label;
    const animation = record.animation;
    const legacyCustom = (!animation || animation.kind === 'authored_station') && c.id === 'custom';
    const url = animation?.url || (legacyCustom ? task.concept_url : null);
    media('machine-result',url,animation?.poster || task.concept_poster);
    $('machine-result').hidden = !url;
    $('machine-caption').textContent = url ? (animation?.evidence || 'Pre-run authored CAD animation; not validated machine execution.') : 'This historical snapshot has no task-matched 3D clip. Its former schematic is not displayed.';
    $('human-cost').textContent = money(r.human_cost_usd); $('station-cost').textContent = money(r.station_cost_usd);
    breakdown('human-breakdown',r.accounting.human); breakdown('station-breakdown',r.accounting.station);
    const delta = r.station_cost_usd-r.human_cost_usd;
    $('cost-direction').textContent = `Selected machine is ${money(Math.abs(delta))} ${delta >= 0 ? 'more' : 'less'} per task under these assumptions.`;
    $('metrics').textContent = `Assumed machine throughput: ${(3600/r.assumptions.station_elapsed_seconds).toFixed(1)} accepted tasks/hour at 100% assumed acceptance. Hands-on labor: ${r.assumptions.station_attended_seconds}s/task. Actual first-pass yield, rework and accepted throughput are unknown.`;
    $('next-measurement').textContent = r.next_action;
    $('assumptions').textContent = JSON.stringify(r.assumptions,null,2);
    $('limitations').replaceChildren(...[...r.limitations,...(animation?.limitations || [])].map(s => node('li',s)));
    sources($('research-sources'));
    $('download-report').href = `/api/fastening/runs/${record.id}/export`;
    $('snapshot-status').textContent = `Saved ${record.id}; reopening repeats no calls.`;
    history.replaceState(null,'','#'+record.id); show(2);
  }
  function openRecord() {
    error('');
    if (record.status === 'failed') {
      task=record.task; $('task-picker').value=task.id; taskDetails(); candidates(); show(1);
      error(record.error); history.replaceState(null,'','#'+record.id);
      $('flow-status').textContent='Analysis incomplete; failure and sources saved. No fallback recommendation.';
    } else render();
  }
  async function perform(fn) {
    if (busy) return;
    busy=true; error(''); document.querySelectorAll('button,select').forEach(b => b.disabled=true);
    try { await fn(); } catch(e) { error(e.message); $('flow-status').textContent='Could not complete this action; saved evidence remains available.'; }
    finally { busy=false; document.querySelectorAll('button,select').forEach(b => b.disabled=false); $('review-change').disabled=!config?.tavily_configured || !config?.agent_configured; }
  }
  async function run() {
    show(1); record=null; candidates();
    $('flow-status').textContent='Tavily research → reasoning agent selects the machine → estimate and task-matched 3D animation…';
    record=await api(`/api/fastening/runs?task_id=${encodeURIComponent(task.id)}`,true);
    openRecord(); await savedList();
    if (record.status !== 'failed') { show(1); $('flow-status').textContent='Agent decision and sources saved. The side-by-side comparison is ready.'; }
  }
  $('task-picker').onchange=selectTask;
  $('review-change').textContent='Analyze task →'; $('review-change').onclick=()=>perform(run);
  $('change-scenario').textContent='← Review agent decision'; $('change-scenario').onclick=()=>show(1);
  $('view-comparison').onclick=()=>show(2);
  $('saved-analysis').onchange=()=>perform(async()=>{if (!$('saved-analysis').value) return; record=await api('/api/fastening/runs/'+$('saved-analysis').value); openRecord();});
  document.querySelectorAll('#journey button').forEach(b=>b.onclick=()=>show(Number(b.dataset.step)===2&&(!record?.estimate||record.status==='failed')?1:Number(b.dataset.step)));
  $('pause-both').onclick=pause;
  $('play-both').onclick=()=>perform(async()=>{pause();const videos=[$('human-result'),$('machine-result')].filter(v=>!v.hidden);videos.forEach(v=>{v.currentTime=0;v.muted=true;});await Promise.all(videos.map(v=>v.play()));});
  (async()=>{
    try {
      const id=location.hash.slice(1); config=await api('/api/fastening/config');
      config.tasks.forEach(t=>$('task-picker').add(new Option(t.demo_label || t.label,t.id)));
      selectTask(); const ready=config.tavily_configured && config.agent_configured;
      $('research-readiness').textContent=ready?'Automatic Tavily research and GMI reasoning are configured.':'Server configuration needed: Tavily and GMI credentials are required.';
      $('review-change').disabled=!ready; await savedList();
      if (/^[a-f0-9]{32}$/.test(id)) {record=await api('/api/fastening/runs/'+id);openRecord();} else show(0);
    } catch(e) {error(e.message);}
  })();
})();
