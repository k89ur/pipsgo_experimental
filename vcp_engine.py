from __future__ import annotations
from typing import Callable, Optional
import numpy as np
import pandas as pd
import rs_engine
from nse_latest_data import install_nse_latest_close
install_nse_latest_close(rs_engine)
DEFAULT_BATCH_SIZE = rs_engine.DEFAULT_BATCH_SIZE
QUALITY_PRESETS = {"Strict": {"swing_window": 4, "progress_tolerance": .10, "volume_tolerance": .05}, "Standard": {"swing_window": 4, "progress_tolerance": .18, "volume_tolerance": .10}, "Loose": {"swing_window": 3, "progress_tolerance": .28, "volume_tolerance": .18}}

def _clean(frame):
    if frame is None or frame.empty or not {"Close","High","Low","Volume"}.issubset(frame.columns): return pd.DataFrame()
    x=frame[["Close","High","Low","Volume"]].copy(); x.index=pd.to_datetime(x.index,errors="coerce")
    if getattr(x.index,"tz",None) is not None: x.index=x.index.tz_localize(None)
    x=x[~x.index.isna()].sort_index()
    for c in x.columns: x[c]=pd.to_numeric(x[c],errors="coerce")
    x=x.replace([np.inf,-np.inf],np.nan).dropna(subset=["Close","High","Low"]); x=x[x.Close>0]; x["Volume"]=x.Volume.fillna(0).clip(lower=0); return x

def _extrema(x,window):
    hi=x.High.rolling(window*2+1,center=True).max(); lo=x.Low.rolling(window*2+1,center=True).min(); pts=[]
    for i in range(window,len(x)-window):
        h,l=float(x.High.iloc[i]),float(x.Low.iloc[i])
        if h>=float(hi.iloc[i])*(1-1e-9): pts.append((i,"H",h))
        if l<=float(lo.iloc[i])*(1+1e-9): pts.append((i,"L",l))
    pts.sort(key=lambda z:z[0]); out=[]
    for p in pts:
        if not out or out[-1][1]!=p[1]: out.append(p)
        else:
            old=out[-1]; out[-1]=p if ((p[1]=="H" and p[2]>=old[2]) or (p[1]=="L" and p[2]<=old[2])) else old
    return out

def _candidate_contractions(x,window,lookback=180):
    start=max(0,len(x)-lookback); y=x.iloc[start:].reset_index(drop=False); pts=_extrema(y,window); out=[]
    for j in range(len(pts)-2):
        p1,p2,p3=pts[j:j+3]
        if p1[1]!="H" or p2[1]!="L" or p3[1]!="H" or not(p1[0]<p2[0]<p3[0]): continue
        high,low,recovery=float(p1[2]),float(p2[2]),float(p3[2])
        depth=(high-low)/high*100 if high>0 else np.nan
        if not(1<=depth<=40): continue
        seg=y.iloc[p1[0]:p3[0]+1]
        out.append({"high_i":start+p1[0],"low_i":start+p2[0],"recover_i":start+p3[0],"high":high,"low":low,"recovery_high":recovery,"depth":depth,"avg_volume":float(seg.Volume.mean())})
    return out

def _choose_sequence(candidates,minimum,maximum,first_max,final_max,tolerance):
    best=[]
    for end in range(len(candidates)):
        for start in range(max(0,end-6),end+1):
            seq=candidates[start:end+1]
            if not(minimum<=len(seq)<=maximum): continue
            # Consecutive contractions intentionally share the prior recovery high.
            if any(seq[k]["recover_i"]>seq[k+1]["high_i"] for k in range(len(seq)-1)): continue
            depths=[c["depth"] for c in seq]
            if depths[0]>first_max or depths[-1]>final_max: continue
            if any(depths[k+1]>depths[k]*(1+tolerance) for k in range(len(depths)-1)): continue
            if any(seq[k+1]["recovery_high"]<seq[k]["recovery_high"]*(.75-tolerance) for k in range(len(seq)-1)): continue
            if len(seq)>len(best) or (len(seq)==len(best) and seq[-1]["recover_i"]>(best[-1]["recover_i"] if best else -1)): best=seq
    return best

def _trend_ok(x):
    c=x.Close; m50=c.rolling(50).mean(); m150=c.rolling(150).mean(); m200=c.rolling(200).mean()
    if any(pd.isna(v) for v in (m50.iloc[-1],m150.iloc[-1],m200.iloc[-1])): return False
    return bool(c.iloc[-1]>m50.iloc[-1]>m150.iloc[-1]>m200.iloc[-1])

def analyze_vcp(symbol,frame,min_contractions=2,max_contractions=4,first_max=25.,final_max=5.,final_min_tightness=0.,volume_required=True,near_high_pct=7.,min_price=100.,min_avg_volume=0.,trend_filter=True,near_pivot_pct=5.,breakout_already_occurred=False,quality="Standard"):
    x=_clean(frame)
    if len(x)<253: return {}
    p=QUALITY_PRESETS.get(quality,QUALITY_PRESETS["Standard"]); seq=_choose_sequence(_candidate_contractions(x,p["swing_window"]),min_contractions,max_contractions,first_max,final_max,p["progress_tolerance"])
    close,today_high=float(x.Close.iloc[-1]),float(x.High.iloc[-1]); avgvol=float(x.Volume.tail(50).mean()); prior=float(x.High.iloc[-253:-1].max()); from52=(today_high-prior)/prior*100 if prior else np.nan
    if seq:
        depths=[c["depth"] for c in seq]; vols=[c["avg_volume"] for c in seq]; pivot=max(c["recovery_high"] for c in seq); pdist=(pivot-close)/pivot*100 if pivot else np.nan; final=depths[-1]; volcontract=all(vols[i+1]<=vols[i]*(1+p["volume_tolerance"]) for i in range(len(vols)-1)); breakout=close>pivot*1.005; finaltight=final_min_tightness<=final<=final_max
    else: depths=[]; pivot=pdist=final=np.nan; volcontract=breakout=finaltight=False
    trend=_trend_ok(x); highok=from52>=-near_high_pct; pivotok=bool(np.isfinite(pdist) and pdist<=near_pivot_pct and pdist>=-25); breakoutok=breakout if breakout_already_occurred else not breakout
    qualified=bool(seq and finaltight and (volcontract if volume_required else True) and close>=min_price and avgvol>=min_avg_volume and highok and pivotok and breakoutok and (trend or not trend_filter))
    score=min(30,len(seq)*10)+(20 if depths and all(depths[i+1]<=depths[i]*1.10 for i in range(len(depths)-1)) else 0)+(20 if finaltight else 0)+(15 if volcontract else 0)+(10 if trend else 0)+(5 if pivotok else 0)
    return {"Symbol":symbol,"LTP":close,"VCP":qualified,"Quality":quality,"Contractions":len(seq),"C1 %":depths[0] if depths else np.nan,"C2 %":depths[1] if len(depths)>1 else np.nan,"C3 %":depths[2] if len(depths)>2 else np.nan,"C4 %":depths[3] if len(depths)>3 else np.nan,"Final Contraction %":final,"Pivot":pivot,"From Pivot %":pdist,"52W High":prior,"From 52W High %":from52,"Avg Volume 50D":avgvol,"Volume Contracting":volcontract,"Trend OK":trend,"Breakout":breakout,"VCP Score":score,"History Days":len(x)}

def run_scan(min_contractions=2,max_contractions=4,first_max=25.,final_max=5.,final_min_tightness=0.,volume_required=True,near_high_pct=7.,min_price=100.,min_avg_volume=0.,trend_filter=True,near_pivot_pct=5.,breakout_already_occurred=False,quality="Standard",batch_size=DEFAULT_BATCH_SIZE,snapshot_mode="eod",force_refresh=False,progress_callback:Optional[Callable]=None):
    symbols=rs_engine.get_nse_symbols(); snap=rs_engine._download_universe(symbols,batch_size=batch_size,snapshot_mode=snapshot_mode,force_refresh=force_refresh,progress_callback=progress_callback); rows=[]
    for done,(symbol,frame) in enumerate(snap["data"].items(),1):
        try:
            r=analyze_vcp(symbol,frame,min_contractions,max_contractions,first_max,final_max,final_min_tightness,volume_required,near_high_pct,min_price,min_avg_volume,trend_filter,near_pivot_pct,breakout_already_occurred,quality)
            if r: rows.append(r)
        except Exception: pass
        if progress_callback and (done==1 or done%100==0 or done==len(snap["data"])): progress_callback(done,max(len(symbols),len(snap["data"])),f"Analysing VCP · {done:,}/{len(snap['data']):,}")
    if not rows: raise RuntimeError("No usable stock data was returned for VCP analysis.")
    df=pd.DataFrame(rows); df=df[df.VCP].copy().sort_values(["VCP Score","Contractions","From Pivot %"],ascending=[False,False,True]).reset_index(drop=True)
    if not df.empty:
        meta=rs_engine._sector_industry_results(df.Symbol.astype(str).tolist()); inds=rs_engine._stock_index_results(df.Symbol.astype(str).tolist()); df["Industry"]=[meta.get(s,("Not Available","Not Available"))[1] for s in df.Symbol.astype(str)]; df["Index"]=[" • ".join(v for v in inds.get(s,("Not Available",)*5) if v!="Not Available") or "Not Available" for s in df.Symbol.astype(str)]
    df["TradingView"]="https://www.tradingview.com/chart/?symbol=NSE%3A"+df.Symbol.astype(str)
    cols=["Symbol","Index","Industry","LTP","VCP Score","Quality","Contractions","C1 %","C2 %","C3 %","C4 %","Final Contraction %","Pivot","From Pivot %","52W High","From 52W High %","Avg Volume 50D","Volume Contracting","Trend OK","Breakout","History Days","TradingView"]; df=df[[c for c in cols if c in df.columns]]
    stats={"universe":len(symbols),"downloaded":snap["downloaded"],"coverage":snap["usable_coverage"],"usable":snap["usable"],"missing_count":snap["missing_count"],"short_history_count":snap["short_history_count"],"stale_data_count":snap["stale_data_count"],"data_date":snap["data_date"],"snapshot_mode":snap["mode"],"snapshot_day":snap["snapshot_day"],"downloaded_at":snap["downloaded_at"],"total_candidates":len(rows),"matches":len(df)}
    return df,stats
