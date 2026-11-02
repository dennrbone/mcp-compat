"""Рисунки рукописи из проверенных фактических сводок."""

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams['svg.hashsalt']='mcp-compat-publication'
ROOT=Path('experiments/publication-2026-11-03')
COLORS=dict(B2='#878787',B3='#b8b8b8',M1='#2c6493',D0='#af7647',D1='#35816b',B2V='#7d5a94')


def draw(axes,summary,methods,prefix=''):
    for ax,metric,title in zip(axes,['CRR','UHR'],['Правильное восстановление','Ошибочные исполнения']):
        rates=[summary[m]['overall'][metric] for m in methods]
        bars=ax.bar(methods,[np.nan if r['value'] is None else r['value'] for r in rates],color=[COLORS[m] for m in methods])
        for bar,rate in zip(bars,rates):
            label='н/д' if rate['value'] is None else f"{rate['numerator']}/{rate['denominator']}"
            height=.01 if rate['value'] is None else bar.get_height()
            ax.annotate(label,(bar.get_x()+bar.get_width()/2,height),ha='center',va='bottom',xytext=(0,4),textcoords='offset points',fontsize=8)
        ax.set_ylim(0,1.12)
        ax.set_yticks([0,.25,.5,.75,1],['0%','25%','50%','75%','100%'])
        ax.set_title(prefix+title,fontsize=10)
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',alpha=.18)
        ax.set_axisbelow(True)
        assert len(bars)==len(methods) and all(r['value'] is None or np.isfinite(b.get_height()) for r,b in zip(rates,bars))
    axes[0].set_ylabel('Доля случаев')


def save(figure,name):
    figure.savefig(f'docs/figures/{name}.png',dpi=220)
    figure.savefig(f'docs/figures/{name}.svg',metadata={'Date':None})
    plt.close(figure)


if __name__ == '__main__':
    data=json.loads((ROOT/'declared-comparison'/'analysis.json').read_bytes())
    fig,axes=plt.subplots(1,2,figsize=(9,3.8),layout='constrained')
    draw(axes,data['summary'],['B2','B3','M1','D0','D1'])
    fig.suptitle('Готовые правила миграции: источник операций и допуск',fontsize=12)
    save(fig,'declared-controls')
    root=ROOT/'case-study'/'analysis'
    if all((root/regime/'repeated-and-replay.json').exists() for regime in ('with-rules','without-rules')):
        fig,axes=plt.subplots(2,2,figsize=(11,7),layout='constrained')
        for row,regime,label in [(0,'with-rules','С готовыми правилами'),(1,'without-rules','Без готовых правил')]:
            data=json.loads((root/regime/'analysis.json').read_bytes())
            derived=json.loads((root/regime/'repeated-and-replay.json').read_bytes())
            summary={**data['summary'],**derived['replay']['summary']}
            draw(axes[row],summary,['B3','D0','D1','B2','M1','B2V'],label+'\n')
        fig.suptitle('Прикладные API: три повтора; B2V — проверка тех же кандидатов',fontsize=12)
        save(fig,'case-study-comparison')
