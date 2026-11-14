"""Exhort benchmark: sabotaged MLPs (10 of 32 neurons killed) healed three ways, plus a broken XON LM.
Run: python scripts/exhort_bench.py"""
import torch, torch.nn as nn, copy, numpy as np
from xon.exhort import *
from xon.lm.model import LMConfig, XONLM
lf=lambda mod,b: ((mod(b[0])-b[1])**2).mean()
def mlp_case(seed):
    torch.manual_seed(seed)
    X=torch.randn(768,4); Y=(torch.sin(X[:,:1]*2)+X[:,1:2]*X[:,2:3])
    m=nn.Sequential(nn.Linear(4,32),nn.ReLU(),nn.Linear(32,1))
    opt=torch.optim.Adam(m.parameters(),1e-2)
    for i in range(300):
        l=lf(m,(X[:512],Y[:512])); opt.zero_grad(); l.backward(); opt.step()
    with torch.no_grad(): m[0].bias[:10]=-50   # kill 10 of 32 neurons (dying-ReLU style)
    tr=[(X[i:i+128],Y[i:i+128]) for i in range(0,512,128)]; va=[(X[512:],Y[512:])]
    return m,tr,va
res={"no exhort (just keep training)":[], "random rebirth":[], "Exhort (gradient-guided)":[]}
for seed in range(5):
    m,tr,va=mlp_case(seed)
    a=copy.deepcopy(m); heal(a,tr,lf,150,5e-3); res["no exhort (just keep training)"].append(float(lf(a,va[0]).detach()))
    b=copy.deepcopy(m); r=exhort(b,tr,va,lf,ExhortConfig(max_frac=0.4,candidates=1,birth_step=0.0,heal_steps=150,heal_lr=5e-3,useless_q=0)); res["random rebirth"].append(r["val_after"])
    c=copy.deepcopy(m); r=exhort(c,tr,va,lf,ExhortConfig(max_frac=0.4,candidates=8,heal_steps=150,heal_lr=5e-3,useless_q=0)); res["Exhort (gradient-guided)"].append(r["val_after"])
    print(seed, 'found',r['found'],'kept',r['kept'])
for k,v in res.items(): print(f"{k:34s} val MSE mean {np.mean(v):.4f}")
cfg=LMConfig(vocab_size=64,d_model=32,n_layers=2,n_heads=2,n_kv_heads=1,seq_len=32)
lm=XONLM(cfg); ids=np.array([i%17 for i in range(4000)])
with torch.no_grad(): lm.blocks[0].ffn.w1.weight[:5]=0; lm.blocks[1].ffn.w2.weight[0,3]=float('inf')
r=exhort(lm,lm_batches(ids,32,40),lm_batches(ids,32,4,seed=5),lm_loss,ExhortConfig(heal_steps=40,heal_lr=3e-3))
print("LM:",{k:r[k] for k in ('neurons','found','broken','dead','useless','reborn','kept','reason')})
