
(function(){
  var K='arabic-site-theme';
  var saved=null; try{saved=localStorage.getItem(K);}catch(e){}
  var t=saved||(window.matchMedia&&matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  document.documentElement.setAttribute('data-theme',t);
  document.addEventListener('DOMContentLoaded',function(){
    var b=document.getElementById('theme'); if(!b)return;
    var set=function(v){document.documentElement.setAttribute('data-theme',v);
      b.innerHTML=v==='dark'?'&#9728;':'&#9789;'; try{localStorage.setItem(K,v);}catch(e){}};
    set(document.documentElement.getAttribute('data-theme'));
    b.addEventListener('click',function(){
      set(document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark');});
  });
  /* self-check miss tally */
  document.addEventListener('DOMContentLoaded',function(){
    var boxes=document.querySelectorAll('.missbox');
    if(!boxes.length)return;
    var t=document.createElement('div'); t.className='tally';
    t.innerHTML='<span>Missed <b>0</b> / '+boxes.length+'</span><button type="button">reset</button>';
    document.body.appendChild(t);
    var num=t.querySelector('b');
    function upd(){
      var n=0; boxes.forEach(function(b){if(b.checked)n++;});
      num.textContent=n; t.classList.toggle('on',n>0);
    }
    boxes.forEach(function(b){b.addEventListener('change',upd);});
    upd();
    t.querySelector('button').addEventListener('click',function(){
      boxes.forEach(function(b){b.checked=false;}); upd();});
  });
})();
