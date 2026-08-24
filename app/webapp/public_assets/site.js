(()=>{
  function setupUI(){
    const style=document.createElement('style');
    style.textContent=`
      .logo{width:52px!important;height:52px!important;display:block!important;object-fit:contain!important;object-position:center!important;border-radius:50%!important;background:#07122e!important;box-shadow:0 0 0 1px rgba(108,181,255,.38),0 0 32px rgba(46,153,255,.34)!important}
      .btn,.navbtn{-webkit-appearance:none!important;appearance:none!important;-webkit-tap-highlight-color:transparent!important;-webkit-touch-callout:none!important;touch-action:manipulation!important;user-select:none!important;-webkit-user-select:none!important;outline:none!important;font-family:inherit!important;text-decoration:none!important}
      button.btn,button.navbtn{border-style:solid;line-height:1;position:relative;overflow:hidden}
      button.btn:focus,button.btn:focus-visible,button.navbtn:focus,button.navbtn:focus-visible{outline:none!important}
      button.btn::after,button.navbtn::after{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 20%,rgba(255,255,255,.14) 48%,transparent 76%);transform:translateX(-130%);transition:transform .42s ease;pointer-events:none}
      button.btn:hover::after,button.navbtn:hover::after{transform:translateX(130%)}
      button.btn:active,button.navbtn:active{transform:scale(.985)!important}
      @media(max-width:620px){.logo{width:48px!important;height:48px!important}.brand{gap:12px!important}}
    `;
    document.head.appendChild(style);

    const logo=document.querySelector('img.logo');
    if(logo){
      logo.removeAttribute('srcset');
      logo.src='/assets/clarify-logo.webp?v=20260824-2';
      logo.alt='Clarify';
      logo.decoding='async';
      logo.loading='eager';
    }

    document.querySelectorAll('a.btn,a.navbtn').forEach(anchor=>{
      const href=anchor.getAttribute('href');
      if(!href)return;
      const button=document.createElement('button');
      button.type='button';
      button.className=anchor.className;
      button.innerHTML=anchor.innerHTML;
      button.setAttribute('aria-label',(anchor.textContent||'').trim());
      button.dataset.href=href;
      anchor.replaceWith(button);
      button.addEventListener('click',()=>{
        if(button.disabled)return;
        button.classList.add('pressed');
        const target=button.dataset.href||'/';
        window.setTimeout(()=>window.location.assign(target),70);
      });
    });
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setupUI,{once:true});
  else setupUI();

  if(matchMedia('(prefers-reduced-motion:reduce)').matches)return;
  const c=document.getElementById('fx');
  if(!c)return;
  const x=c.getContext('2d');
  let w,h,d,p=[];
  function r(){
    d=Math.min(devicePixelRatio||1,1.5);w=innerWidth;h=innerHeight;
    c.width=w*d;c.height=h*d;x.setTransform(d,0,0,d,0,0);
    const n=w<700?25:48;
    p=Array.from({length:n},()=>({x:Math.random()*w,y:Math.random()*h,vx:(Math.random()-.5)*.12,vy:(Math.random()-.5)*.12,a:.15+Math.random()*.28}));
  }
  function f(){
    x.clearRect(0,0,w,h);
    for(let i=0;i<p.length;i++){
      const q=p[i];q.x+=q.vx;q.y+=q.vy;
      if(q.x<0)q.x=w;if(q.x>w)q.x=0;if(q.y<0)q.y=h;if(q.y>h)q.y=0;
      x.fillStyle='rgba(112,188,255,'+q.a+')';x.beginPath();x.arc(q.x,q.y,1.2,0,7);x.fill();
      for(let j=i+1;j<p.length;j++){
        const z=p[j],dx=q.x-z.x,dy=q.y-z.y,s=dx*dx+dy*dy;
        if(s<9000){x.strokeStyle='rgba(93,151,255,'+((1-s/9000)*.05)+')';x.beginPath();x.moveTo(q.x,q.y);x.lineTo(z.x,z.y);x.stroke();}
      }
    }
    requestAnimationFrame(f);
  }
  r();addEventListener('resize',r,{passive:true});f();
})();
