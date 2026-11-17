import io, re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
st.set_page_config(page_title="MDT & ERMAI",layout="wide")
st.title("MDT & ERMAI RTP Analysis Dashboard")
st.caption("PETRONAS CARIGALI | Petrophysics Operations")

def n(s): return re.sub(r"[^a-z0-9]+"," ",str(s).lower()).strip()
def read_mdt(f):
    if f.name.lower().endswith(".csv"): raw=pd.read_csv(f,header=None)
    else: raw=pd.read_excel(f,header=None,engine="openpyxl")
    aliases={"File No.":["file no","file number"],"Test No.":["test no","test number"],"Probe MD m":["probe md","probe md m"],"Probe TVD m":["probe tvd","probe tvd m"],"DD Mobility mD/cP":["dd mobility","drawdown mobility"],"Packer/Probe Type":["packer probe type","probe type"],"Pretest Quality Flag/Status":["pretest quality flag status","pretest quality status"]}
    scores=[]
    for i,row in raw.iloc[:40].iterrows(): scores.append((sum(any(n(v)==n(a) for a in [k]+vls) for k,vls in aliases.items() for v in row),i))
    hi=max(scores)[1]; heads=[]
    for v in raw.iloc[hi]:
        heads.append(next((k for k,vls in aliases.items() if n(v) in [n(x) for x in [k]+vls]),str(v)))
    df=raw.iloc[hi+1:].copy();df.columns=heads
    for c in ["File No.","Test No.","Probe MD m","Probe TVD m","DD Mobility mD/cP"]:
        if c in df: df[c]=pd.to_numeric(df[c],errors="coerce")
    return df.dropna(subset=["File No.","Test No.","Probe MD m"]).reset_index(drop=True)
def read_las(f):
    lines=f.getvalue().decode(errors="replace").splitlines(); curves=[]; start=None; null=-999.25
    sec=""
    for i,s in enumerate(lines):
        s=s.strip()
        if s.upper().startswith("~C"):sec="C";continue
        if s.upper().startswith("~A"):start=i+1;break
        if sec=="C" and s and not s.startswith("#"):curves.append(re.split(r"[. ]",s)[0].upper())
        if s.upper().startswith("NULL"):
            try:null=float(s.split(":")[0].split()[-1])
            except:pass
    if start is None: raise ValueError("No ~ASCII section")
    amap={"depth":["DEPTH","DEPT","MD","DEPTH_MD"],"phit":["PHIT_ERMAI","PHIT","TOTAL_POROSITY"],"perm":["PERM_ERMAI","PERM","PERMEABILITY"],"vclw":["VCLW_ERMAI","VCLW","WET_CLAY_VOLUME"],"prob":["PT_PROBABILITY","PTPROBABILITY","PT_PROB"]}
    ix={k:next((i for i,x in enumerate(curves) if x in a),-1) for k,a in amap.items()}
    if min(ix.values())<0:raise ValueError("Required RTP curve missing")
    rows=[]
    for s in lines[start:]:
        if not s.strip() or s.lstrip().startswith("#"):continue
        try:
            t=s.split();r={k:float(t[j]) for k,j in ix.items()};r={k:(np.nan if abs(v-null)<1e-9 else v) for k,v in r.items()};rows.append(r)
        except:continue
    return pd.DataFrame(rows).sort_values("depth").reset_index(drop=True)
def actual(s,inc_s,inc_u):
    x=n(s)
    if x in ["valid","valid test"]:return "VALID"
    if x in ["dry test","lost seal","no seal","tight test","invalid"] or (inc_s and x=="supercharged") or (inc_u and x in ["unstabilized","unstabilized test"]):return "INVALID"
    return None
def match(mdt,rtp,c,inc_s,inc_u):
    d=rtp.depth.to_numpy();out=[]
    for _,m in mdt.iterrows():
        j=int(np.abs(d-m["Probe MD m"]).argmin());r=rtp.iloc[j];a=actual(m["Pretest Quality Flag/Status"],inc_s,inc_u);p="N/A" if r.isna().any() else ("VALID" if r.prob>=c else "INVALID")
        out.append({"File No.":m["File No."],"Test No.":m["Test No."],"Probe MD":m["Probe MD m"],"MDT Status":m["Pretest Quality Flag/Status"],"RTP Depth":r.depth,"PHIT":r.phit,"Perm":r.perm,"VCLW":r.vclw,"PT Probability":r.prob,"Actual":a,"ERMAI Flag":p})
    return pd.DataFrame(out)
a,b=st.columns(2)
fm=a.file_uploader("MDT XLSX/CSV",type=["xlsx","csv"]);fl=b.file_uploader("ERMAI LAS/TXT",type=["las","txt"])
if not fm or not fl:st.info("Upload both files to start.");st.stop()
try:mdt=read_mdt(fm);rtp=read_las(fl)
except Exception as e:st.error(str(e));st.stop()
inc_s=st.toggle("Include Supercharged as Invalid");inc_u=st.toggle("Include Unstabilized as Invalid")
rows=[]
for c in np.arange(0,1.001,.01):
    x=match(mdt,rtp,c,inc_s,inc_u);x=x[x.Actual.notna()&x["ERMAI Flag"].ne("N/A")];ok=(x.Actual==x["ERMAI Flag"]);rows.append([c,int(ok.sum()),len(x),ok.mean() if len(x) else 0])
scan=pd.DataFrame(rows,columns=["Cut-off","Correct","Evaluated","Accuracy"]);opt=float(scan.loc[scan.Accuracy.idxmax(),"Cut-off"]);c=st.slider("PT Probability cut-off",0.,1.,opt,.01);x=match(mdt,rtp,c,inc_s,inc_u);sc=x[x.Actual.notna()&x["ERMAI Flag"].ne("N/A")]
m1,m2,m3=st.columns(3);m1.metric("MDT records",len(mdt));m2.metric("RTP rows",len(rtp));m3.metric("Accuracy",f"{(sc.Actual==sc['ERMAI Flag']).mean():.2%}" if len(sc) else "N/A")
t1,t2,t3=st.tabs(["Cut-off","Cross-validation","Depth window"])
with t1:
 f=go.Figure(go.Scatter(x=scan["Cut-off"],y=scan.Accuracy*100));f.add_vline(x=c,line_dash="dash",line_color="orange");st.plotly_chart(f,use_container_width=True);st.dataframe(scan,use_container_width=True)
with t2:st.dataframe(x,use_container_width=True,height=520)
with t3:
 i=st.selectbox("MDT test",range(len(x)),format_func=lambda i:f"File {x.iloc[i]['File No.']} | Test {x.iloc[i]['Test No.']}");w=st.number_input("Window +/- m",.5,20.,5.,.5);md=x.iloc[i]["Probe MD"];q=rtp[(rtp.depth>=md-w)&(rtp.depth<=md+w)];fig=go.Figure()
 for col in ["prob","phit","vclw","perm"]:fig.add_trace(go.Scatter(x=q[col],y=q.depth,name=col))
 fig.update_yaxes(autorange="reversed");st.plotly_chart(fig,use_container_width=True);st.dataframe(q,use_container_width=True)
st.download_button("Download comparison CSV",x.to_csv(index=False),"comparison.csv")
