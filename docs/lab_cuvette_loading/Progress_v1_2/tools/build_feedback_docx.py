"""Build the compact feedback report from the verified RESULTS.md, then render it.

Run with the Codex bundled Python; the artifact marker and render QA are separate.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT


def clean(text):
    text=re.sub(r'\[([^]]+)\]\(([^)]+)\)',r'\1',text)
    return text.replace('**','').replace('`','')


def build(source, output):
    document=Document()
    section=document.sections[0]
    section.top_margin=section.bottom_margin=Cm(2)
    section.left_margin=section.right_margin=Cm(2.1)
    section.page_width,section.page_height=Cm(21),Cm(29.7)
    for name in ('Normal','Title','Heading 1','Heading 2','Heading 3'):
        style=document.styles[name];style.font.name='Noto Sans CJK SC';style.font.color.rgb=RGBColor(0,0,0)
        style.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Noto Sans CJK SC')
    normal=document.styles['Normal'];normal.font.size=Pt(10)
    normal.paragraph_format.space_after=Pt(6);normal.paragraph_format.line_spacing=1.15
    normal.paragraph_format.widow_control=True
    document.styles['Title'].font.size=Pt(23)
    document.styles['Heading 1'].font.size=Pt(15)
    document.styles['Heading 2'].font.size=Pt(12)
    lines=Path(source).read_text().splitlines();i=0;code=False
    while i<len(lines):
        line=lines[i];i+=1
        if line.startswith('```'):
            code=not code;continue
        if not line.strip():continue
        if line.startswith('|') and not code:
            rows=[line]
            while i<len(lines) and lines[i].startswith('|'):
                rows.append(lines[i]);i+=1
            values=[[clean(c.strip()) for c in row.strip('|').split('|')] for row in rows
                if not re.match(r'^\|\s*[-:]+\s*\|',row)]
            table=document.add_table(rows=0,cols=len(values[0]));table.autofit=False
            widths=[16.8/len(values[0])]*len(values[0])
            if len(widths)==2:widths=[4.6,12.2]
            if len(widths)==3:widths=[6.6,4.5,5.7]
            if len(widths)==4:widths=[5.0,4.0,3.7,4.1]
            if len(widths)==5:widths=[3.3,4.5,2.5,3.2,3.3]
            for column,width in zip(table.columns,widths):
                column.width=Cm(width)
            for j,row in enumerate(values):
                cells=table.add_row().cells
                for k,(cell,text) in enumerate(zip(cells,row)):
                    cell.width=Cm(widths[k]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    p=cell.paragraphs[0];p.paragraph_format.space_after=Pt(4);p.paragraph_format.space_before=Pt(4)
                    run=p.add_run(text);run.font.size=Pt(9)
                    if j==0:run.bold=True
                    pr=cell._tc.get_or_add_tcPr()
                    borders=OxmlElement('w:tcBorders')
                    for edge in ('top','left','bottom','right'):
                        el=OxmlElement('w:'+edge);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'4');el.set(qn('w:color'),'D9D9D9');borders.append(el)
                    pr.append(borders)
                    if j==0:
                        sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'E8EDF2');pr.append(sh)
                    margins=OxmlElement('w:tcMar')
                    for edge in ('top','left','bottom','right'):
                        m=OxmlElement('w:'+edge);m.set(qn('w:w'),'90');m.set(qn('w:type'),'dxa');margins.append(m)
                    pr.append(margins)
                if j==0:
                    trpr=table.rows[j]._tr.get_or_add_trPr();header=OxmlElement('w:tblHeader');trpr.append(header)
                trpr=table.rows[j]._tr.get_or_add_trPr()
                trpr.append(OxmlElement('w:cantSplit'))
            document.add_paragraph();continue
        if line.startswith('# '):document.add_paragraph(clean(line[2:]),'Title');continue
        if line.startswith('## '):document.add_paragraph(clean(line[3:]),'Heading 1');continue
        if line.startswith('### '):document.add_paragraph(clean(line[4:]),'Heading 2');continue
        p=document.add_paragraph()
        if code:
            p.paragraph_format.space_after=Pt(2)
            r=p.add_run(line);r.font.name='DejaVu Sans Mono';r.font.size=Pt(8)
        else:
            p.add_run(clean(line))
    document.core_properties.title='LabSim Progress v1 2 修订验证报告'
    document.core_properties.subject='器皿装载任务的在线与离线进度诊断'
    document.core_properties.author='LabSim'
    # The bundled Word base template includes a blue Title rule. This report
    # uses plain black type and whitespace, without inherited paragraph rules.
    for tree in (document._element,document.styles.element):
        for element in list(tree.xpath('.//w:pBdr')):
            element.getparent().remove(element)
    document.save(output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();build(a.source,a.output)
