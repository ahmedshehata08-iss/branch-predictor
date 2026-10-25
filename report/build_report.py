#!/usr/bin/env python3
"""Author: Ahmed Ahmed. Rebuild the report from source and recorded run evidence."""
from pathlib import Path
import csv
import json
import textwrap
import html
import math
import os
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
# Embed real fonts so PDF viewers do not substitute incompatible metrics.
runtime=Path(os.environ.get('CODEX_PRIMARY_RUNTIME_ROOT','/opt/codex/runtimes/codex-primary-runtime'))
font_roots=[Path('/usr/share/fonts/truetype/liberation2'),
            Path('/usr/share/fonts/truetype/liberation'),
            runtime/'dependencies/native/libreoffice-headless/libreoffice/share/fonts/truetype']
font_root=next((p for p in font_roots if (p/'LiberationSerif-Regular.ttf').exists()),None)
if font_root is None:
    raise RuntimeError('Install Liberation Serif/Mono fonts (e.g. fonts-liberation2).')
for label,filename in [('ReportSerif','LiberationSerif-Regular.ttf'),
                       ('ReportSerifBold','LiberationSerif-Bold.ttf'),
                       ('ReportSerifItalic','LiberationSerif-Italic.ttf'),
                       ('ReportSerifBoldItalic','LiberationSerif-BoldItalic.ttf'),
                       ('ReportMono','LiberationMono-Regular.ttf')]:
    pdfmetrics.registerFont(TTFont(label,str(font_root/filename)))
pdfmetrics.registerFontFamily('ReportSerif',normal='ReportSerif',bold='ReportSerifBold',
                              italic='ReportSerifItalic',boldItalic='ReportSerifBoldItalic')
pdfmetrics.registerFontFamily('ReportMono',normal='ReportMono',bold='ReportMono',
                              italic='ReportMono',boldItalic='ReportMono')
OUT=ROOT/'report'; ASSETS=OUT/'assets'; ASSETS.mkdir(exist_ok=True)
summary=json.loads((ROOT/'results/summary.json').read_text())
rows=list(csv.DictReader((ROOT/'results/benchmark_results.csv').open()))
by={}
for row in rows: by.setdefault(row['benchmark'],{})[row['predictor']]=row
pm=[v['pm'] for v in by.values()]
HITS=sum(int(r['global_hits']) for r in pm)
COND=summary['pm']['conditional']
HIT_MISSES=sum(int(r['hit_mispredictions']) for r in pm)
FALL_MISSES=sum(int(r['fallback_mispredictions']) for r in pm)
source_manifest=[]

MONO='/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
SANS='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

def source_image(name,path,start,end,phase):
    source=(ROOT/path).read_text().splitlines()
    end=min(end,len(source))
    selected=source[start-1:end]
    # Dedenting and tab expansion change only display whitespace.
    code=textwrap.dedent('\n'.join(selected)).expandtabs(4)
    lines=code.splitlines()
    width=1500; font_size=25; left=115; pad=34
    while max(ImageFont.truetype(MONO,font_size).getlength(x) for x in lines)>width-left-pad:
        font_size-=1
    font=ImageFont.truetype(MONO,font_size)
    small=ImageFont.truetype(SANS,24)
    step=max(29,font_size+5); top=70
    height=top+step*len(lines)+26
    im=Image.new('RGB',(width,height),'#f8fafc');d=ImageDraw.Draw(im)
    band='#334155' if phase=='Initial Version' else '#174a70'
    d.rectangle((0,0,width,55),fill=band)
    d.text((25,13),f'{path}  |  lines {start}-{end}',font=small,fill='white')
    d.line((88,65,88,height-14),fill='#d3dbe4',width=2)
    for i,line in enumerate(lines):
        y=top+i*step
        d.text((72,y),str(start+i),font=font,fill='#7c8796',anchor='ra')
    for i, line in enumerate(lines):
        colour = '#517248' if line.lstrip().startswith(('//', '# ')) else '#15283b'
        d.text((left,top+i*step),line,font=font,fill=colour)
    d.rectangle((0,0,width-1,height-1),outline='#cbd5e1',width=2)
    dest=ASSETS/(name+'.png');im.save(dest)
    source_manifest.append({'asset':dest.name,'source':path,'first_line':start,'last_line':end,'display_font_pt':font_size/3})
    return dest

snaps={}
for name,path,start,end,phase in [
 ('01_state_before','baseline/my_predictor.h',57,67,'Initial Version'),
 ('01_state_after','src/my_predictor.h',61,88,'My Version'),
 ('02_constructor_before','baseline/my_predictor.h',66,67,'Initial Version'),
 ('02_constructor_after','src/my_predictor.h',90,112,'My Version'),
 ('03_predict_before','baseline/my_predictor.h',69,78,'Initial Version'),
 ('03_predict_after','src/my_predictor.h',114,138,'My Version'),
 ('04_update_before','baseline/my_predictor.h',80,82,'Initial Version'),
 ('04_update_after','src/my_predictor.h',140,161,'My Version'),
 ('05_driver_before','baseline/predict.cc',58,67,'Initial Version'),
 ('05_driver_after','src/predict.cc',33,53,'My Version'),
 ('06_runner_before','baseline/run',13,23,'Initial Version'),
 ('06_runner_after','run',13,26,'My Version'),
 ('07_io_before','baseline/trace.cc',426,435,'Initial Version'),
 ('07_io_after','src/trace.cc',429,440,'My Version'),
 ('08_quote_before','baseline/trace.cc',439,447,'Initial Version'),
 ('08_quote_after','src/trace.cc',446,460,'My Version')]:
    snaps[name]=source_image(name,path,start,end,phase)
(ASSETS/'snapshot_manifest.json').write_text(json.dumps(source_manifest,indent=2)+'\n')

# Plot uses measured values only; the much larger static baseline is in the table.
fig,ax=plt.subplots(figsize=(7.5,3.1))
labels=['Bimodal','Hybrid (this work)','Supplied gshare']
values=[summary[k]['mean_mpki'] for k in ['bimodal','pm','gshare']]
bar=ax.bar(labels,values,color=['#a4afbd','#174a70','#61a3a0'],width=.55)
ax.set_ylabel('Mean MPKI (lower is better)');ax.set_ylim(0,12)
ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.22);ax.set_axisbelow(True)
for b,v in zip(bar,values):ax.text(b.get_x()+b.get_width()/2,v+.18,f'{v:.3f}',ha='center',fontsize=11)
fig.tight_layout();fig.savefig(ASSETS/'dynamic_predictor_comparison.png',dpi=220);plt.close(fig)

# A captured terminal excerpt from the actual log, not invented command output.
log=(ROOT/'results/test_output.txt').read_text().splitlines()
selected=[x for x in log if x.startswith('PASS ')]
# The sanitizer repeats the first 16 cases; show the first test suite only.
selected=selected[:26]
font=ImageFont.truetype(MONO,25);h=90+34*len(selected)
im=Image.new('RGB',(1500,h),'#13202c');d=ImageDraw.Draw(im)
d.text((30,22),'Captured test output (excerpt)',font=ImageFont.truetype(SANS,28),fill='#a5d8ff')
for i,line in enumerate(selected):d.text((30,75+34*i),line,font=font,fill='#e2eaf2')
im.save(ASSETS/'test_output.png')

W,H=612,792;LEFT=55;RIGHT=557;WIDTH=RIGHT-LEFT
pdf=OUT/'Ahmed_Ahmed_Branch_Prediction_Report.pdf'
c=canvas.Canvas(str(pdf),pagesize=(W,H));c.setTitle('Branch Predictor Implementation - Ahmed Ahmed')
c.setAuthor('Ahmed Ahmed');c.setSubject('Computer Architecture Assignment 1: hybrid branch prediction')
c.setCreator('Ahmed Ahmed - reproducible report builder')
styles={
 'body':ParagraphStyle('body',fontName='ReportSerif',fontSize=11,leading=14.5,spaceAfter=8),
 'small':ParagraphStyle('small',fontName='ReportSerif',fontSize=9.4,leading=12.2),
 'caption':ParagraphStyle('caption',fontName='ReportSerifItalic',fontSize=9,leading=11.5,textColor=colors.HexColor('#435268')),
 'cell':ParagraphStyle('cell',fontName='ReportSerif',fontSize=9.2,leading=11.2),
 'headcell':ParagraphStyle('headcell',fontName='ReportSerifBold',fontSize=9,leading=11,textColor=colors.white),
 'code':ParagraphStyle('code',fontName='ReportMono',fontSize=9,leading=12),
}
page=0;y=0;page_titles=[]
def para(text,style='body',gap=8):
    global y
    p=Paragraph(text,styles[style]);_,height=p.wrap(WIDTH,1000)
    if y-height<53:raise RuntimeError(f'Page {page} overflow at: {text[:75]} (y={y}, height={height})')
    p.drawOn(c,LEFT,y-height);y-=height+gap

def title(text):
    global y
    c.setFont('ReportSerifBold',17);c.setFillColor(colors.HexColor('#172b40'));c.drawString(LEFT,y,text);y-=27

def sub(text):
    global y
    y-=8
    c.setFillColor(colors.HexColor('#172b40'));c.setFont('ReportSerifBold',12.2);c.drawString(LEFT,y,text);y-=20

def new_page(section,heading):
    global page,y
    if page:c.showPage()
    page+=1;page_titles.append(heading)
    c.setFillColor(colors.HexColor('#3d4a58'));c.setFont('ReportSerif',9.4)
    c.drawString(LEFT,754,'Computer Architecture');c.drawRightString(RIGHT,754,'Assignment 1: Branch Predictor')
    c.setStrokeColor(colors.HexColor('#9aa8b8'));c.setLineWidth(.6);c.line(LEFT,746,RIGHT,746)
    c.line(LEFT,43,RIGHT,43);c.setFont('ReportSerif',9)
    c.drawString(LEFT,30,'Ahmed Ahmed');c.drawCentredString(W/2,30,section);c.drawRightString(RIGHT,30,f'Page {page}')
    y=721;title(heading)

def image(path,width=WIDTH,caption=None,maxheight=None):
    global y
    with Image.open(path) as im:iw,ih=im.size
    height=ih*width/iw
    if maxheight and height>maxheight:width*=maxheight/height;height=maxheight
    if y-height<53:raise RuntimeError(f'Page {page} image overflow: {path.name}, y={y}, h={height}')
    c.drawImage(str(path),LEFT+(WIDTH-width)/2,y-height,width=width,height=height,mask='auto')
    y-=height+8
    if caption:para(caption,'caption',gap=9)

def table(headers,data,widths,font=9.2):
    global y
    head=[Paragraph(str(x),styles['headcell']) for x in headers]
    body=[[Paragraph(str(v),styles['cell']) for v in row] for row in data]
    t=Table([head]+body,colWidths=widths,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#234962')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f0f4f7')]),
        ('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#234962')),
        ('LINEBELOW',(0,-1),(-1,-1),.5,colors.HexColor('#a4b3c2'))]))
    _,height=t.wrap(WIDTH,1000)
    if y-height<53:raise RuntimeError(f'Page {page} table overflow, y={y}, h={height}')
    t.drawOn(c,LEFT,y-height);y-=height+13

def command(text):
    para(html.escape(text).replace('\n','<br/>'),'code',gap=10)

new_page('1 INTRODUCTION','1  Introduction')
para('<b>Branch Predictor Implementation</b><br/>Author: <b>Ahmed Ahmed</b><br/>October 25, 2026',gap=14)
para('<b>GitHub repository:</b><br/><link href="https://github.com/ahmedshehata08-iss/branch-predictor" color="#174a70">https://github.com/ahmedshehata08-iss/branch-predictor</link>','small',gap=10)
para('In this assignment, I completed the <font name="ReportMono">pm_predictor</font> class in the supplied CBP2 infrastructure. I combined a bimodal predictor with a tagged, two-way global predictor so that a global hit supplies the direction prediction and a global miss uses the bimodal result.')
para('The original class predicted every branch as taken and did not update any state. I added the tables, two-bit counters, global history, tag matching, allocation, and least-recently-used replacement. I also added repeatable tests and measurements for all 20 supplied traces.')
sub('What works')
for text in [
 'A 4,096-entry bimodal predictor and a 512-set, two-way global predictor.',
 'Valid/tag checks, global-hit priority, saturating counters, and invalid-first/LRU replacement.',
 'Actual-outcome history updates and isolation of unconditional branches.',
 'Original single-trace use, a portable suite runner, exact statistics, and four predictor comparisons.']:
    para('&#8226; '+text,gap=5)
sub('Measured outcome')
para(f'The completed hybrid averaged <b>{summary["pm"]["mean_mpki"]:.3f} MPKI</b> and achieved <b>{summary["pm"]["pooled_accuracy_pct"]:.2f}%</b> pooled conditional-branch accuracy. Mean MPKI fell by <b>91.59%</b> relative to the original always-taken behavior and by <b>29.51%</b> relative to bimodal alone. The supplied, larger gshare predictor averaged {summary["gshare"]["mean_mpki"]:.3f} MPKI and was better overall.')
sub('Scope')
para('I implemented the required direction-prediction subset. I did not implement the optional loop predictor, PIR, branch targets, BTB, indirect target cache, or complete extra-credit predictor. This is an educational Pentium M-style model, not a claim of exact commercial-hardware behavior.')
para('The report follows the supplied sample: introduction, code changes labeled <b>Initial Version</b> and <b>My Version</b>, then tests and results. Every code image is rendered from the actual packaged source with its original line numbers.','small')

new_page('2 DESIGN','2  Predictor design and assumptions')
table(['Component','Default organization / policy'],[
 ['Bimodal','4,096 counters; two logical bits each; initialized to 1 (weakly not taken).'],
 ['Global','512 sets x 2 ways; each entry has a valid bit, 6-bit tag, and two-bit counter.'],
 ['History','15 actual conditional outcomes; initial value 0.'],
 ['Replacement','Prefer an invalid way; otherwise evict LRU. One victim bit per set.'],
 ['Counter decision','0 or 1 predicts not taken; 2 or 3 predicts taken.'],
 ['New global entry','Allocate on every global miss; initialize to 2 for T or 1 for NT.'],
 ['Training','Always train bimodal for conditional branches; train the hit entry or allocate on a miss.']],[115,387])
sub('Indexing and prediction')
command('bimodal_index = PC & 0xFFF\nhash = (PC ^ GHR) & 0x7FFF\nrow = hash >> 6                 # HASH[14:6]\ntag = hash & 0x3F               # HASH[5:0]\nfinal = global[row][hit_way] if valid_tag_hit else bimodal[index]')
para('I use raw PC bits in the default model, matching the main assignment diagram. The Appendix B teaching example shifts the PC by two bits; I expose that as a separate small configuration rather than mixing its address convention into the default benchmark model.')
sub('Update order and storage')
para('The driver predicts, scores the prediction, and then updates using the actual outcome. I retain the lookup fields in <font name="ReportMono">pm_update</font>, train the counters, refresh LRU, and finally shift the outcome into GHR. Nonconditional branches do not change this state.')
para('Logical predictor state is 4,096 x 2 + 512 x 2 x (1 + 6 + 2) + 512 + 15 = <b>17,935 bits</b> (about 2.19 KiB). This excludes simulator bookkeeping. The C++ representation uses bytes, integers, vectors, and padding, so its host memory usage is larger.','small')

new_page('3 CODE CHANGES','3.1  Saved lookup fields and table state')
para('I expanded the update record to preserve the exact lookup used during prediction. I also introduced global entries, table storage, and an LRU victim array. The original class had no predictor tables or history.')
sub('Initial Version')
image(snaps['01_state_before'])
sub('My Version')
image(snaps['01_state_after'],caption='Figure 1. Original state declaration and the new prediction context/table declarations.')
para('A global hit requires both <font name="ReportMono">valid</font> and a matching tag. The <font name="ReportMono">way = -1</font> value marks a miss and selects the bimodal fallback. Keeping row, tag, and index in the update object prevents training a different entry after history changes.','small')

new_page('3 CODE CHANGES','3.2  Initialization and saturating counters')
para('I replaced the empty constructor with deterministic initialization. All bimodal counters start weakly not taken; global entries start invalid. Constructor parameters allow small test configurations while the no-argument constructor retains the assignment sizes.')
sub('Initial Version')
image(snaps['02_constructor_before'])
sub('My Version')
image(snaps['02_constructor_after'],caption='Figure 2. Constructor and shared two-bit training helper.')
table(['Current counter','After NT','After T','Prediction before update'],[
 ['0','0','1','NT'],['1','0','2','NT'],['2','1','3','T'],['3','2','3','T']],[110,90,90,212])
para('The counter saturates at 0 and 3. On allocation I set a fresh weak state for the observed outcome; I do not inherit a replacement victim\'s old bias. The assignment leaves this policy open, so I document it explicitly.','small')

new_page('3 CODE CHANGES','3.3  Global lookup and final prediction')
para('I replaced unconditional taken prediction with the required hybrid selection. Both global ways are checked. A matching valid tag wins even when the bimodal counter disagrees; otherwise the bimodal prediction is returned.')
sub('Initial Version')
image(snaps['03_predict_before'])
sub('My Version')
image(snaps['03_predict_after'],caption='Figure 3. Prediction before and after implementation. The target remains zero by design.')
para('Prediction reads the tables without training them. Unconditional branches return taken immediately. The global hash uses the history that existed before the current branch outcome became known.','small')

new_page('3 CODE CHANGES','3.4  Training, allocation, LRU, and history')
para('I implemented the previously empty update function. Every conditional outcome trains the indexed bimodal counter. A global hit trains the matched entry; a miss allocates an invalid entry or replaces the least recently used way.')
sub('Initial Version')
image(snaps['04_update_before'])
sub('My Version')
image(snaps['04_update_after'],caption='Figure 4. The complete hybrid update path.')
para('For two ways, one victim bit is sufficient for exact LRU: after using way 0, way 1 becomes the victim; after using way 1, way 0 becomes the victim. I refresh this state on both hits and allocations.')
para('The last operation shifts the <b>actual</b> outcome into the masked history register. The update uses saved lookup indices, not a newly calculated hash. The serial driver resolves each branch immediately, so only one prediction context is outstanding.')

new_page('3 CODE CHANGES','3.5  Measurement and comparison controls')
para('I kept direction scoring before update and added exact conditional counts, accuracy, and separate global-hit/fallback miss counts. The driver accepts <font name="ReportMono">pm</font>, <font name="ReportMono">bimodal</font>, <font name="ReportMono">gshare</font>, or <font name="ReportMono">always_taken</font>; its default remains the required hybrid.')
sub('Initial Version')
image(snaps['05_driver_before'])
sub('My Version')
image(snaps['05_driver_after'],caption='Figure 5. Conditional direction scoring and measured diagnostics.')
para('The existing three-decimal MPKI line is preserved. With <font name="ReportMono">--stats</font>, a JSON line records exact counts and higher-precision metrics. I removed target-miss reporting from the main experiment because branch targets are outside the required scope.','small')
para('The always-taken control matches the starter <font name="ReportMono">pm_predictor</font> behavior. The supplied 32,768-entry gshare algorithm is retained as a reference; the new bimodal-only control uses the same 4,096 counters and initial state as the hybrid fallback.','small')

new_page('3 CODE CHANGES','3.6  Portable run and reproducible build')
para('The original runner required csh and dc. I replaced it with Python 3, preserving sorted trace execution and the average-MPKI result. Commands are passed as argument lists, and a failed child process stops the run.')
sub('Initial Version')
image(snaps['06_runner_before'])
sub('My Version')
image(snaps['06_runner_after'],caption='Figure 6. Original csh aggregation and the Python runner\'s corresponding loop.')
para('I updated the Makefile to compile C++17 with warnings and added separate <font name="ReportMono">test</font> and <font name="ReportMono">sanitize</font> targets. A dedicated comparison script records all 80 runs, their exact outputs, and a CSV result table.')
para('The main build produces only the required <font name="ReportMono">predict</font> program. The inherited <font name="ReportMono">cpm_predictor</font> remains an unimplemented optional stub, available only through the explicitly named <font name="ReportMono">extra-credit</font> target. This prevents it being mistaken for a completed submission.','small')

new_page('3 CODE CHANGES','3.7  Trace opening and error handling')
para('While validating the command line, I found that the original trace reader continued after a failed file open. I added an immediate error exit, checked reads of the compression signature, and used a const decompressor string. The trace-decoding algorithm remains unchanged.')
sub('Initial Version')
image(snaps['07_io_before'])
sub('My Version')
image(snaps['07_io_after'],caption='Figure 7. File-open and compression-signature handling.')
para('I also replaced <font name="ReportMono">fclose(tracefp)</font> with <font name="ReportMono">pclose(tracefp)</font> and check its return status. A failed gzip/bzip2 process now makes the program fail instead of printing a misleading successful MPKI result.')
para('The CLI tests include a missing filename and a broken bzip2 stream. These checks cover the entry points changed here; the inherited decoder is still intended for valid supplied CBP2 data and is not a complete malformed-record validator.','small')

new_page('3 CODE CHANGES','3.8  Trace filenames with spaces or quotes')
para('The original reader inserted the filename directly into a fixed-size shell command. I changed it to a dynamically sized string and quote the filename as one shell argument, including embedded apostrophes. This makes ordinary paths with spaces work reliably.')
sub('Initial Version')
image(snaps['08_quote_before'])
sub('My Version')
image(snaps['08_quote_after'],caption='Figure 8. Decompressor command construction and launch.')
para('The integration test creates a compressed trace whose filename contains both spaces and an apostrophe, runs the actual driver, and checks the branch counts and accuracy. It also checks that the original single-trace command still prints one MPKI line.')
para('The before snapshots throughout this section come from byte-for-byte copies of the supplied files in <font name="ReportMono">baseline/</font>. The complete change set is available in <font name="ReportMono">results/code_changes.patch</font>; the images show the relevant excerpts rather than every unchanged line.','small')

new_page('4 VALIDATION','4.1  Directed tests and independent reference')
para('I checked the predictor with deterministic cases before interpreting benchmark performance. All <b>16 directed tests passed</b>, and the C++ output matched an independent Python dictionary/LRU model for <b>40,000 events</b> across four configurations.')
table(['Test group','What I verified'],[
 ['Initialization and counters','Table sizes, invalid startup, all 8 saturating transitions.'],
 ['Addressing','Default hash fields, masked history, saved prediction indices, expected hash aliasing.'],
 ['Lookup and selection','Invalid matching tags miss; valid wrong tags miss; global hits override bimodal in both directions.'],
 ['Update and replacement','Both components train on a hit; invalid ways fill first; replacement resets the counter; hits refresh LRU.'],
 ['History and branch type','Actual outcomes shift once; wrapping is correct; unconditional branches leave direction state unchanged.'],
 ['Pattern and configuration','Alternating branch pattern is learned; invalid configurations are rejected; first six Appendix B hashes match.']],[135,367])
sub('Independent model')
para('The reference test uses per-set ordered dictionaries to maintain recency, rather than reproducing the C++ victim-array representation. A fixed seed (20261025) generates 10,000 events for each of four configurations: (12,9,6,0), (4,2,2,2), (2,1,1,0), and (8,4,3,1). The tuple means bimodal bits, set bits, tag bits, and PC shift.')
para('Each event compares the final prediction, row, tag, hit way, post-update history, selected bimodal counter, and LRU victim. Streams mix conditional and nonconditional branches, small colliding PCs, and full 32-bit addresses.')
sub('Sanitizers and command line')
para('AddressSanitizer and UndefinedBehaviorSanitizer passed all directed cases. Leak detection was disabled because the execution container blocks its process inspection; I do not claim a successful leak scan. Four CLI groups check compressed paths/metrics, legacy output, invalid arguments/missing files, and decompression failures.')

new_page('4 VALIDATION','4.2  Captured test output')
para('This image is an excerpt of the actual successful test run saved in <font name="ReportMono">results/test_output.txt</font>. The complete log also contains the compiler commands and the sanitizer run.')
image(ASSETS/'test_output.png',caption='Figure 9. Captured output from the directed, differential, and command-line tests.',maxheight=485)
command('make -C src test\nmake -C src sanitize')
para('The final build uses g++ 13.3.0 and Python 3.12.14 in the execution environment. It completed without compiler warnings. The tests and all benchmark commands are included so that the results can be checked on another compatible machine.','small')

new_page('4 VALIDATION','4.3  Worked trace using the teaching configuration')
para('I ran the Appendix B branch sequence through the actual C++ predictor with 16 bimodal counters, four sets, two ways, two-bit tags, and PC shifted right by two. Here all bimodal counters start at 1 and allocated global counters start at 2/1, as in my implementation. These reset/allocation rules differ from the appendix\'s prefilled counters, so the predictions below are my measured results.','small')
toy=list(csv.DictReader((ROOT/'results/toy_trace.csv').open()))
headers=['#','Br.','Act.','GHR','XOR','Row','Tag','Hit','Pred.','OK']
data=[[r['step'],r['branch'],'T' if r['actual']=='1' else 'NT',r['ghr_before'],r['hash'],r['row'],r['tag'],'Y' if r['global_hit']=='True' else 'N','T' if r['prediction']=='1' else 'NT','Y' if r['correct']=='True' else 'N'] for r in toy]
# Dense exact mapping; smaller padding retains readability for all 23 observations.
old=styles['cell'];styles['cell']=ParagraphStyle('toycell',parent=old,fontSize=8.5,leading=9.2)
table(headers,data,[30,40,45,65,65,45,50,45,60,57])
styles['cell']=old
para('For example, the first branch has PC 0x44: (0x44 &gt;&gt; 2) &amp; 0xF = 0001. XOR with GHR 0000 gives 0001, hence row 0/tag 01. No valid global tag exists, so the initial bimodal state predicts NT. After actual T, GHR becomes 0001.','small')

new_page('5 RESULTS','5.1  Experimental method and metric definitions')
para('I ran every supplied trace from a fresh predictor state, once for each of four predictors, for <b>80 completed runs</b>. There is no warm-up exclusion and no parameter tuning by benchmark. Each trace represents 100 million instructions according to the supplied CBP2 documentation, so the suite represents 2 billion instructions per predictor.')
table(['Predictor','Role','Logical counter capacity'],[
 ['Always taken','Original pm stub behavior','No adaptive counter table'],
 ['Bimodal','Fallback-only control','4,096 x 2 bits = 8,192 bits'],
 ['Gshare','Supplied reference algorithm','32,768 x 2 bits = 65,536 bits, plus 15 history bits'],
 ['Hybrid (pm)','Completed assignment','4,096 bimodal + 1,024 global counters; tags/valid/LRU/history included in 17,935 bits']],[100,145,257])
sub('Metrics')
command('MPKI = direction_misses / instructions * 1000\nAccuracy (%) = (conditional_branches - misses) / conditional_branches * 100\nGlobal hit rate (%) = global_hits / conditional_branches * 100')
para('MPKI uses <b>instructions</b>, not conditional branch count. Accuracy uses <b>conditional branches</b>. All 20 instruction windows are equal length, so the arithmetic mean of per-trace MPKI also equals suite-wide MPKI. Pooled accuracy uses summed misses and summed conditional branches; it is not an unweighted average of percentages.')
para('For synthetic traces I check exact counts and accuracy. The driver\'s fixed 100-million denominator is valid only for the supplied benchmark windows. Using it on an arbitrary short trace would not give meaningful instruction-normalized MPKI.')
sub('Comparison limits')
para('The gshare control has substantially more counter storage. I report it as a supplied reference, not as an equal-budget contest. Its counters begin strongly not taken (0), following the original code; bimodal and hybrid begin weakly not taken (1). The small teaching configuration is used only for tests, not for these benchmark results.')

new_page('5 RESULTS','5.2  Complete benchmark MPKI results')
para('Lower MPKI is better. Values below are rounded to three decimals for display; calculations and the packaged CSV retain the measured precision.','small')
data=[]
for name,v in by.items():data.append([name]+[f'{float(v[k]["mpki"]):.3f}' for k in ['always_taken','bimodal','gshare','pm']])
data.append(['<b>Mean</b>']+[f'<b>{summary[k]["mean_mpki"]:.3f}</b>' for k in ['always_taken','bimodal','gshare','pm']])
table(['Benchmark','Always taken','Bimodal','Gshare','Hybrid (pm)'],data,[130,93,90,90,99])
para('The hybrid improves on bimodal in <b>19 of 20</b> traces. The exception is 300.twolf: 22.046 MPKI for hybrid versus 21.942 for bimodal. It beats supplied gshare only on 256.bzip2, which has very few misses under all dynamic predictors.','small')

new_page('5 RESULTS','5.3  Exact hybrid counts and prediction-source use')
data=[]
for name,v in by.items():
    r=v['pm'];data.append([name,f'{int(r["conditional"]):,}',f'{int(r["misses"]):,}',f'{float(r["accuracy_pct"]):.3f}%',f'{100*int(r["global_hits"])/int(r["conditional"]):.2f}%'])
table(['Benchmark','Conditional','Dir. misses','Accuracy','Global hits'],data,[112,112,100,89,89])
para(f'Across the suite, the hybrid makes <b>{summary["pm"]["misses"]:,}</b> direction errors out of <b>{COND:,}</b> conditional branches. A global hit supplies <b>{HITS:,}</b> predictions ({100*HITS/COND:.2f}%); the remaining {COND-HITS:,} use the bimodal fallback.','small')
para(f'Of the direction errors, {HIT_MISSES:,} occur on global hits and {FALL_MISSES:,} on fallback predictions. The corresponding observed error rates are {100*HIT_MISSES/HITS:.2f}% and {100*FALL_MISSES/(COND-HITS):.2f}%. These subsets contain different branch contexts; their rates alone do not establish a causal improvement for every branch.','small')

new_page('5 RESULTS','5.4  Interpretation of the measured results')
image(ASSETS/'dynamic_predictor_comparison.png',caption='Figure 10. Mean MPKI of the three dynamic predictors. Capacities are not equal.')
table(['Comparison','Measured change for hybrid'],[
 ['Versus starter always taken','91.59% fewer misses per instruction'],
 ['Versus bimodal-only','29.51% lower mean MPKI; 19/20 trace wins'],
 ['Versus supplied gshare','15.12% higher mean MPKI; 1/20 trace wins']],[210,292])
para('The hybrid is useful because the bimodal table learns a branch\'s general bias while global entries learn particular PC/history combinations. I see strong improvements over bimodal in workloads such as mcf (33.245 to 17.680), jess (8.809 to 1.750), and eon (9.405 to 3.139 MPKI).')
para('Gshare performs better overall in this experiment. A plausible contributor is its larger direct-indexed table, while the hybrid must manage two-way conflicts and partial-tag aliasing. This is an interpretation, not a separately isolated causal measurement; I did not run a matched-storage study.')
para('The twolf regression also shows that global priority is not automatically beneficial on every trace. A valid hit is allowed to override a correct bimodal prediction, exactly as the assignment specifies. The result should not be presented as a universal accuracy improvement or as a measured CPU speedup.')

new_page('6 REPRODUCTION','6  Reproduction and submission contents')
sub('Build, check, and reproduce')
command('make -C src\nmake -C src test\nmake -C src sanitize\n./run traces\npython3 run_comparison.py')
para('The no-argument Makefile target builds the required predictor. The comparison script preserves exact per-run stdout, all counts, and summaries. gzip and bzip2 must be installed at the locations configured in <font name="ReportMono">src/trace.h</font>.')
table(['Path','Purpose'],[
 ['src/my_predictor.h','Required hybrid class and comparison predictors'],
 ['src/predict.cc','Driver and conditional-direction metrics'],
 ['tests/','Directed, reference-model, and CLI checks'],
 ['traces/','20 supplied compressed traces, unchanged'],
 ['baseline/','Original files used for before snapshots'],
 ['results/benchmark_results.csv','All 80 measured benchmark rows'],
 ['results/raw_runs.json','Commands and actual output for every benchmark run'],
 ['results/test_output.txt','Captured successful build/test/sanitizer log'],
 ['results/toy_trace.csv','Measured 23-event teaching example'],
 ['results/code_changes.patch','Full diff of changed starter files'],
 ['report/','This PDF, source snapshots, plot, and report builder'],
 ['README.md','Author, dependencies, choices, limits, and submission instructions']],[200,302])
para('I keep the source code, report, README, tests, and measured results together in my GitHub repository: <link href="https://github.com/ahmedshehata08-iss/branch-predictor" color="#174a70">https://github.com/ahmedshehata08-iss/branch-predictor</link>. The original infrastructure attribution remains in place.','small')

new_page('7 CONCLUSION','7  Requirement review and conclusion')
table(['Assignment requirement','Evidence / status'],[
 ['Implement pm_predictor member functions','Completed constructor, predict, and update; Figures 1-4.'],
 ['Bimodal and global outcome prediction','Completed 4,096-counter bimodal and tagged two-way global predictor.'],
 ['Global hit determines final outcome','Implemented explicitly; tested with disagreement in both directions.'],
 ['Two-way option instead of four-way','Used as allowed in the assignment highlights.'],
 ['PIR/loop/targets may be skipped','Excluded; no target or extra-credit completion claimed.'],
 ['Build and run supplied infrastructure','Build and 80 trace runs completed; full outputs included.'],
 ['Code, report, README for GitHub','Included together; repository link is on page 1 and in the README.'],
 ['Before/after snapshots and author','Eight labeled snapshot pairs; author Ahmed Ahmed in code and report.']],[209,293])
para('I replaced the starter behavior with a working hybrid direction predictor and verified its lookup, training, replacement, and history rules. The complete trace results show a substantial improvement over the starter and over bimodal-only prediction, with a clear tradeoff against the larger supplied gshare reference.')
sub('Limitations')
para('The model has partial-tag aliasing, a single outstanding prediction context, no speculation recovery, and no target/loop/PIR structures. The policy choices are stated rather than presented as undisclosed Pentium M internals. MPKI alone does not measure execution time, energy, or power savings.','small')
sub('Sources and attribution')
para('[1] Supplied <i>programming-branch-predictor.pdf</i>, Assignment 1, especially the scope/diagram on page 2 and Appendix B.<br/>[2] Supplied <i>cbp2-infrastructure-v2</i>, source, traces, README, and doc/index.html; documentation credits Daniel A. Jimenez.<br/>[3] <i>Sample_Tomasulo_Assignment_Report(2).pdf</i>, used only for report structure and before/after presentation.<br/>No external cache implementation was used. The bundled <i>milenkovic_WDDD02.pdf</i> is titled <i>Demystifying Intel Branch Predictors</i> and is not the 2009 paper named in the assignment; the assignment\'s supplied diagram is the basis of this implementation.','small',gap=0)
c.save()
(OUT/'page_manifest.json').write_text(json.dumps({'pages':page,'titles':page_titles},indent=2)+'\n')
print(f'Created {pdf} ({page} pages)')
