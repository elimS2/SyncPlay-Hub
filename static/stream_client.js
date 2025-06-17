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
  // debug log disabled
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
  }else if(act==='tick'){
     if('idx' in data && data.idx!==idx){ idx=data.idx; loadCurrent(false); }
     if(typeof data.position==='number'){
        const delta=data.position - video.currentTime;
        if(Math.abs(delta)>0.3){
           // large drift -> hard seek
           video.currentTime = data.position;
           video.playbackRate = 1;
        }else{
           // small drift -> gently nudge using playbackRate
           const maxRateShift = 0.05; // ±5 % inaudible
           if(Math.abs(delta) < 0.02){
              video.playbackRate = 1; // in sync
           }else{
              const factor = Math.max(-maxRateShift, Math.min(maxRateShift, delta * 0.5));
              video.playbackRate = 1 + factor;
           }
        }
     }
     if('paused' in data){ paused=data.paused; if(!paused) maybePlay(); else video.pause(); }
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
   // debug
   if(!paused&&enabled){ video.muted=false; video.play().then(()=>console.log('play started')).catch(err=>console.warn(err)); }
} 