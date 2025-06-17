const video=document.getElementById('player');
const evtSource=new EventSource(`/api/stream_feed/${STREAM_ID}`);
let firstInitHandled=false;
let queue=[];
let idx=0;
let paused=true;
let enabled=false;
const overlay=document.getElementById('startOverlay');

evtSource.onmessage=e=>{
  const data=JSON.parse(e.data);
  console.log('SSE', data);
  if(data.init&&!firstInitHandled){
     const st=data.init;
     queue=st.queue;
     idx=st.idx;
     paused=st.paused;
     loadCurrent(false);
     firstInitHandled=true;
     return;
  }
  const act=data.action;
  if(act==='play'){
     if('position' in data) video.currentTime=data.position;
     paused=false;
     maybePlay();
  }else if(act==='pause'){
     if('position' in data) video.currentTime=data.position;
     paused=true; video.pause();
  }else if(act==='seek'){
     if(typeof data.position==='number') video.currentTime=data.position;
     if('idx' in data){ idx=data.idx; }
     if('paused' in data){ paused=data.paused; if(!paused) maybePlay(); else video.pause(); }
  }else if(act==='next'){
     if('idx' in data){ idx=data.idx;} else {idx++;}
     loadCurrent(true);
  }else if(act==='prev'){
     if('idx' in data){ idx=data.idx;} else {idx=Math.max(0,idx-1);} loadCurrent(true);
  }
};

function loadCurrent(autoplay){
  if(idx<0||idx>=queue.length) return;
  const t=queue[idx];
  video.src=t.url;
  if((autoplay||!firstInitHandled)&&!paused){video.muted=true;maybePlay();}
}

if(overlay){
  document.getElementById('startBtn').onclick=()=>{
    enabled=true;
    overlay.style.display='none';
    loadCurrent(true);
  };
}

function maybePlay(){
   console.log('maybePlay paused',paused,'enabled',enabled);
   if(!paused&&enabled){ video.muted=false; video.play().then(()=>console.log('play started')).catch(err=>console.warn(err)); }
} 