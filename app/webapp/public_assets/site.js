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
      .pack-section{margin-top:58px;padding-top:10px}
      .pack-head{max-width:720px;margin-bottom:24px}
      .pack-head h2{margin-bottom:10px}
      .pack-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
      .pack-card{min-height:300px;display:flex;flex-direction:column;padding:25px;border-radius:24px;border:1px solid rgba(118,169,255,.17);background:radial-gradient(circle at 90% 0,rgba(95,80,255,.13),transparent 34%),linear-gradient(180deg,rgba(15,30,68,.78),rgba(7,14,35,.86));box-shadow:inset 0 1px rgba(255,255,255,.035),0 20px 55px rgba(0,0,0,.18)}
      .pack-card.best{border-color:rgba(75,171,255,.5);box-shadow:0 22px 60px rgba(44,105,255,.14),inset 0 1px rgba(255,255,255,.05)}
      .pack-top{display:flex;align-items:center;justify-content:space-between;gap:12px}
      .pack-count{font-size:38px;font-weight:920;letter-spacing:-1.8px;margin:18px 0 4px}
      .pack-price{font-size:25px;font-weight:850;color:#f5f8ff;margin-bottom:16px}
      .pack-copy{color:#a7b5d7;font-size:14px;line-height:1.55;flex:1;margin:0 0 20px}
      .pack-card .btn{width:100%}
      .pack-note{margin-top:16px;color:#8190b5;font-size:13px;line-height:1.55}
      @media(max-width:900px){.pack-grid{grid-template-columns:1fr}}
      @media(max-width:620px){.logo{width:48px!important;height:48px!important}.brand{gap:12px!important}.pack-section{margin-top:42px}.pack-card{min-height:0;padding:22px}.pack-count{font-size:36px}}
    `;
    document.head.appendChild(style);

    const prices=document.querySelector('.prices');
    if(prices && !document.querySelector('.pack-section')){
      const section=document.createElement('div');
      section.className='pack-section';
      section.innerHTML=`
        <div class="pack-head">
          <div class="kicker">Дополнительные запросы</div>
          <h2>Нужно больше <span class="grad">запросов?</span></h2>
          <p class="lead">Докупить запросы можно отдельно от подписки. Они не сгорают и начинают расходоваться только после обычного дневного лимита тарифа.</p>
        </div>
        <div class="pack-grid">
          <div class="pack-card">
            <div class="pack-top"><h3>ПАКЕТ</h3></div>
            <div class="pack-count">+50</div>
            <div class="pack-price">50 ⭐</div>
            <p class="pack-copy">Небольшой запас дополнительных AI-запросов для редких ситуаций, когда дневного лимита не хватило.</p>
            <a class="btn" href="/telegram/open">Купить в Telegram</a>
          </div>
          <div class="pack-card best">
            <div class="pack-top"><h3>ПАКЕТ</h3><span class="badge">ВЫГОДНО</span></div>
            <div class="pack-count">+150</div>
            <div class="pack-price">100 ⭐</div>
            <p class="pack-copy">Оптимальный запас для активного использования Clarify без перехода на более высокий тариф.</p>
            <a class="btn primary" href="/telegram/open">Купить в Telegram</a>
          </div>
          <div class="pack-card">
            <div class="pack-top"><h3>ПАКЕТ</h3></div>
            <div class="pack-count">+500</div>
            <div class="pack-price">250 ⭐</div>
            <p class="pack-copy">Большой несгораемый запас запросов для интенсивной работы и крупных задач.</p>
            <a class="btn" href="/telegram/open">Купить в Telegram</a>
          </div>
        </div>
        <div class="pack-note">⭐ Оплата пакетов Stars проходит внутри Telegram. После покупки запросы автоматически добавляются к аккаунту Clarify.</div>
      `;
      prices.insertAdjacentElement('afterend',section);
    }

    const logo=document.querySelector('img.logo');
    if(logo){
      logo.removeAttribute('srcset');
      logo.src='data:image/webp;base64,UklGRl4DAABXRUJQVlA4IFIDAABwEACdASosACwAPm0wlEekIqIhI4z4gA2JbACsMuz66R60ajS7cC7dt6An2vNbYDK2rjONj6o+Udxg0xz+q/5f8jvhLzqfVn/S9wf9Xv992APRP/Tku8OMdrdurIFtKKSNmxZff9JcPG0HIGt8YUd1VZ725nA9Ich6PZGt8Op6IA1btvv48CRAI9wwAAD+/uJUxFrCe8Y/kkRshvC1r+K5hR9tcKHR+NnNxG/Jmi0qT0+DiuxEVPdvDBhX8ICXOBgc/w0Tuuwb0D1Fcj/sX90NMVb7ePRtFDE2T9g5PRv6qTMOO45yiZ2jf9LABuPfIOL8M1sslt05YRM2M9IbqB1Qbq0VtAhCqUwaH+abcEixX8/yJuaRboBvjOfkgV8SLvDk7vv+cm9psjhjLMBYv4g9qcmZ7uzijX4sAB5Q3+Oj2G+ct3ZaDDIDgIPi1F3iU1kq8rAff3g1mSg7pOj5JYpe03eTdA79jrOx4S2heoohiXwARpmGHfsxcY/48FmlXpJtbQGlP8d+cci3uwt9a7RnWtHzaTsZ+bkKVnGiyWERUc6finNtkr33w3LbSH8NfomXCpXxfhSLxPamp2WBgjy9mv3BYqnP+aE15DbCAdAdGzNdV0x2V+FS4beI1JSsOrEdbIK7g3WmoMowCGqQj2SFdztASEk0LTxbb2ZXNd/YLyEZ/XdSgU7omKVPMAxfzYR6BGl9frZ38CbxX9ecXRGdytCpT/WVvyU5fIzdxrvoKMHNtjJrmfToZvNd8iZsnbAC4b7SJWo3iDs8LPbXLP//37SV9XqZp+f44gEvWLSTuJVN5iqef3KKm36F1aHn/9D+ORF/K5/vGK07XVX7trZyY8/sv6V4t+C2uSl5h85hBwZFhwCKjWIUuHB1PxM2+1Ypt4VdsZhg/1zlkb3z7gXHCs1XjFVvGesUt/V7JdMV11iar/zN1MNaiBeME11tmI+8OaD73KPwgrhYr/hIrKJw3PPD+u83/fixqP4RSFM2+QBfV1FbeG2hPCVNLCybzPE1X/V9jPbCOAC2toEGH+FIrIGy3shypKb4x5utPlAf8hZC98+v2SsByDy4b5i7cGP0FW5g72XX5+gzXDhVQC6tsUxgHfyuOmHLRjo5DqzSXJAA';
      logo.alt='Clarify';
      logo.decoding='sync';
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
