(function(){
  function R(el){return el.shadowRoot||el.attachShadow({mode:'open'});}
  function lib(){return (window.lucide&&window.lucide.icons)||null;}
  var ALIAS={Home:'House',CheckCircle:'CircleCheck',AlertTriangle:'TriangleAlert',MoreHorizontal:'Ellipsis',BarChart:'ChartColumn',BarChart2:'ChartColumn',PieChart:'ChartPie'};
  function pascal(n){return n.replace(/(^|-)([a-z0-9])/g,function(_,__,c){return c.toUpperCase();});}
  function drawIcon(el){
    var L=lib(); if(!L){return false;}
    var name=el.getAttribute('name')||'circle';
    var p=pascal(name);
    var node=L[p]||L[ALIAS[p]]||L.Circle;
    var size=el.getAttribute('size')||20, color=el.getAttribute('color')||'currentColor', sw=el.getAttribute('stroke')||2;
    var kids=(node&&node[2])||[];
    var inner=kids.map(function(c){var a=Object.keys(c[1]).map(function(k){return k+'="'+c[1][k]+'"';}).join(' ');return '<'+c[0]+' '+a+'/>';}).join('');
    R(el).innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="'+size+'" height="'+size+'" viewBox="0 0 24 24" fill="none" stroke="'+color+'" stroke-width="'+sw+'" stroke-linecap="round" stroke-linejoin="round" style="display:block">'+inner+'</svg>';
    return true;
  }
  function defer(el,fn){ if(fn(el))return; var iv=setInterval(function(){ if(fn(el)){clearInterval(iv);} },60); setTimeout(function(){clearInterval(iv);},5000); }
  function def(tag,cls){ if(!customElements.get(tag))customElements.define(tag,cls); }
  def('meto-icon',class extends HTMLElement{
    static get observedAttributes(){return ['name','size','color','stroke'];}
    connectedCallback(){defer(this,drawIcon);}
    attributeChangedCallback(){if(lib())drawIcon(this);}
  });
  function nums(s){return (s||'').split(',').map(function(x){return parseFloat(x);}).filter(function(x){return !isNaN(x);});}
  function drawSpark(el){
    var d=nums(el.getAttribute('data')); if(!d.length)return true;
    var w=+(el.getAttribute('width')||84), h=+(el.getAttribute('height')||34), color=el.getAttribute('color')||'#13B981', fill=el.getAttribute('fill')||'rgba(19,185,129,0.16)';
    var lo=Math.min.apply(0,d), hi=Math.max.apply(0,d);
    var x=function(i){return w*i/(d.length-1);}, y=function(v){return h-3-(h-6)*(hi===lo?0.5:(v-lo)/(hi-lo));};
    var pts=d.map(function(v,i){return x(i)+','+y(v);}).join(' ');
    R(el).innerHTML='<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" style="display:block"><polygon points="0,'+h+' '+pts+' '+w+','+h+'" fill="'+fill+'"/><polyline points="'+pts+'" fill="none" stroke="'+color+'" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="'+x(d.length-1)+'" cy="'+y(d[d.length-1])+'" r="3" fill="'+color+'"/></svg>';
    return true;
  }
  def('meto-spark',class extends HTMLElement{ static get observedAttributes(){return ['data','color','width','height','fill'];} connectedCallback(){drawSpark(this);} attributeChangedCallback(){drawSpark(this);} });
  function drawLine(el){
    var d=nums(el.getAttribute('data')); if(!d.length)return true;
    var w=+(el.getAttribute('width')||330), h=+(el.getAttribute('height')||150), color=el.getAttribute('color')||'#13B981', fill=el.getAttribute('fill')||'rgba(19,185,129,0.14)';
    var band=nums(el.getAttribute('band')), ticks=nums(el.getAttribute('yticks')), xl=(el.getAttribute('xlabels')||'').split(',').filter(Boolean);
    var ymin=el.getAttribute('ymin'), ymax=el.getAttribute('ymax');
    var padL=30,padR=10,padT=12,padB=xl.length?20:8, iw=w-padL-padR, ih=h-padT-padB;
    var lo=ymin!=null?+ymin:Math.min.apply(0,d), hi=ymax!=null?+ymax:Math.max.apply(0,d);
    var x=function(i){return padL+iw*i/(d.length-1);}, y=function(v){return padT+ih*(1-(v-lo)/(hi-lo));};
    var line=d.map(function(v,i){return x(i)+','+y(v);}).join(' ');
    var area=padL+','+(padT+ih)+' '+line+' '+(padL+iw)+','+(padT+ih);
    var tk=ticks.length?ticks:[lo,(lo+hi)/2,hi];
    var g='';
    if(band.length===2){g+='<rect x="'+padL+'" y="'+y(band[1])+'" width="'+iw+'" height="'+Math.max(0,y(band[0])-y(band[1]))+'" fill="rgba(21,145,90,0.14)" rx="6"/>';}
    tk.forEach(function(t){g+='<line x1="'+padL+'" y1="'+y(t)+'" x2="'+(padL+iw)+'" y2="'+y(t)+'" stroke="rgba(16,48,44,0.08)"/><text x="'+(padL-6)+'" y="'+(y(t)+3)+'" text-anchor="end" font-size="9" fill="#5A736D" font-family="JetBrains Mono,monospace">'+t+'</text>';});
    var dots=d.map(function(v,i){return i===d.length-1?'<circle cx="'+x(i)+'" cy="'+y(v)+'" r="5" fill="white" stroke="'+color+'" stroke-width="2.5"/>':'<circle cx="'+x(i)+'" cy="'+y(v)+'" r="2.4" fill="'+color+'" opacity="0.55"/>';}).join('');
    var xlab=xl.map(function(lb,i){return '<text x="'+x(i)+'" y="'+(h-5)+'" text-anchor="middle" font-size="9" fill="#5A736D">'+lb+'</text>';}).join('');
    R(el).innerHTML='<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" style="display:block;overflow:visible">'+g+'<polygon points="'+area+'" fill="'+fill+'"/><polyline points="'+line+'" fill="none" stroke="'+color+'" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'+dots+xlab+'</svg>';
    return true;
  }
  def('meto-line',class extends HTMLElement{ static get observedAttributes(){return ['data','color','width','height','band','yticks','ymin','ymax','xlabels','fill'];} connectedCallback(){drawLine(this);} attributeChangedCallback(){drawLine(this);} });
  function drawBars(el){
    var d=nums(el.getAttribute('data')); if(!d.length)return true;
    var w=+(el.getAttribute('width')||320), h=+(el.getAttribute('height')||130), color=el.getAttribute('color')||'#13B981', xl=(el.getAttribute('xlabels')||'').split(',').filter(Boolean);
    var padL=30,padR=8,padT=10,padB=xl.length?20:8, iw=w-padL-padR, ih=h-padT-padB;
    var hi=Math.max.apply(0,d)*1.1, lo=0;
    var y=function(v){return padT+ih*(1-(v-lo)/(hi-lo));}, slot=iw/d.length;
    var bw=Math.min(34,slot*0.55);
    var bars=d.map(function(v,i){var cx=padL+slot*i+slot/2; var top=y(v); return '<rect x="'+(cx-bw/2)+'" y="'+top+'" width="'+bw+'" height="'+(padT+ih-top)+'" rx="5" fill="'+color+'"/>'+ (xl[i]?'<text x="'+cx+'" y="'+(h-5)+'" text-anchor="middle" font-size="9" fill="#5A736D">'+xl[i]+'</text>':'');}).join('');
    R(el).innerHTML='<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" style="display:block">'+bars+'</svg>';
    return true;
  }
  def('meto-bars',class extends HTMLElement{ static get observedAttributes(){return ['data','color','width','height','xlabels'];} connectedCallback(){drawBars(this);} attributeChangedCallback(){drawBars(this);} });
  function drawRing(el){
    var val=+(el.getAttribute('value')||0), size=+(el.getAttribute('size')||56), sw=+(el.getAttribute('stroke')||6), color=el.getAttribute('color')||'#13B981', track=el.getAttribute('track')||'rgba(16,48,44,0.12)', label=el.getAttribute('label')||'', lc=el.getAttribute('labelcolor')||'#0E2A33';
    var r=(size-sw)/2, c=2*Math.PI*r;
    R(el).innerHTML='<div style="position:relative;width:'+size+'px;height:'+size+'px;display:grid;place-items:center"><svg width="'+size+'" height="'+size+'" style="transform:rotate(-90deg)"><circle cx="'+size/2+'" cy="'+size/2+'" r="'+r+'" fill="none" stroke="'+track+'" stroke-width="'+sw+'"/><circle cx="'+size/2+'" cy="'+size/2+'" r="'+r+'" fill="none" stroke="'+color+'" stroke-width="'+sw+'" stroke-linecap="round" stroke-dasharray="'+c+'" stroke-dashoffset="'+(c*(1-val/100))+'"/></svg><div style="position:absolute;inset:0;display:grid;place-items:center;font-weight:700;font-size:'+(size*0.26)+'px;color:'+lc+'">'+label+'</div></div>';
    return true;
  }
  def('meto-ring',class extends HTMLElement{ static get observedAttributes(){return ['value','size','stroke','color','track','label','labelcolor'];} connectedCallback(){drawRing(this);} attributeChangedCallback(){drawRing(this);} });
  function drawMark(el){
    var size=+(el.getAttribute('size')||40), ring=el.getAttribute('ring')||'#1F6E66', leaf=el.getAttribute('leaf')||'#2FA84E';
    R(el).innerHTML='<svg width="'+size+'" height="'+size+'" viewBox="0 0 96 96" fill="none" style="display:block">'
      +'<path d="M34 71 A30 30 0 1 1 61 69" stroke="'+ring+'" stroke-width="7.5" stroke-linecap="round" fill="none"/>'
      +'<path d="M61 69 C61 77 54 82 47 78" stroke="'+ring+'" stroke-width="7.5" stroke-linecap="round" fill="none"/>'
      +'<path d="M30 66 L33 43 Q34 36 39.5 41.5 L46.5 51 Q48 53.5 49.5 51 L56.5 41.5 Q62 36 63 43 L66 66" stroke="'+ring+'" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
      +'<path d="M49 48 C59 48 64 60 54 70 C45 65 42 55 49 48 Z" fill="'+leaf+'"/>'
      +'<path d="M51 54 C51 61 52 66 53 69" stroke="#EAFBF0" stroke-width="2" stroke-linecap="round" opacity="0.85" fill="none"/>'
      +'</svg>';
    return true;
  }
  def('meto-mark',class extends HTMLElement{ static get observedAttributes(){return ['size','ring','leaf'];} connectedCallback(){drawMark(this);} attributeChangedCallback(){drawMark(this);} });
})();
