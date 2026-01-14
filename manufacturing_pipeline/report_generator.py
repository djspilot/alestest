import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, Image, KeepTogether, PageBreak,
                                 ListFlowable, ListItem)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from svglib.svglib import svg2rlg
from collections import Counter
import os

class PDFReportGenerator:
    def __init__(self, json_path):
        self.json_path = json_path
        self.data = self._load_data()
        
    def _load_data(self):
        with open(self.json_path, 'r') as f:
            return json.load(f)

    def _create_pie_chart(self, data_dict, title="Distribution"):
        drawing = Drawing(400, 200)
        pie = Pie()
        pie.x = 65
        pie.y = 15
        pie.width = 170
        pie.height = 170
        
        # Filter out zero values
        filtered_data = {k: v for k, v in data_dict.items() if v > 0}
        if not filtered_data:
            return None
            
        data = list(filtered_data.values())
        labels = list(filtered_data.keys())
        
        pie.data = data
        pie.labels = labels
        
        # Simple color scheme
        pie.slices.strokeWidth = 0.5
        
        # Add legend
        legend = Legend()
        legend.x = 300
        legend.y = 150
        legend.dx = 8
        legend.dy = 8
        legend.fontName = 'Helvetica'
        legend.fontSize = 10
        legend.boxAnchor = 'nw'
        legend.columnMaximum = 10
        legend.strokeWidth = 1
        legend.strokeColor = colors.black
        legend.deltax = 75
        legend.deltay = 10
        legend.autoXPadding = 5
        legend.yGap = 0
        legend.dxTextSpace = 5
        legend.alignment = 'right'
        legend.dividerLines = 1|2|4
        legend.dividerOffsY = 4.5
        legend.subCols.rpad = 30
        
        # Connect legend to pie
        legend.colorNamePairs = [(pie.slices[i].fillColor, labels[i]) for i in range(len(labels))]
        
        drawing.add(pie)
        drawing.add(legend)
        return drawing

    def _create_bar_chart(self, data_dict, title="Counts"):
        drawing = Drawing(400, 200)
        
        # Filter out zero values
        filtered_data = {k: v for k, v in data_dict.items() if v > 0}
        if not filtered_data:
            return None
            
        data = [list(filtered_data.values())]
        labels = list(filtered_data.keys())
        
        bc = VerticalBarChart()
        bc.x = 50
        bc.y = 50
        bc.height = 125
        bc.width = 300
        bc.data = data
        bc.strokeColor = colors.black
        bc.valueAxis.valueMin = 0
        bc.valueAxis.valueMax = max(data[0]) * 1.1 if data[0] else 10
        bc.valueAxis.valueStep = max(data[0]) // 5 if data[0] and max(data[0]) > 5 else 1
        bc.categoryAxis.labels.boxAnchor = 'ne'
        bc.categoryAxis.labels.dx = 8
        bc.categoryAxis.labels.dy = -2
        bc.categoryAxis.labels.angle = 30
        bc.categoryAxis.categoryNames = labels
        
        drawing.add(bc)
        return drawing

    def _create_section_header(self, text, styles):
        """Create a styled section header."""
        header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            spaceAfter=6,
            spaceBefore=12,
            backColor=colors.Color(0.9, 0.9, 0.95),
            borderPadding=5,
        )
        return Paragraph(text, header_style)

    def _create_info_table(self, data_pairs, col_widths=None):
        """Create a simple two-column info table."""
        if col_widths is None:
            col_widths = [150, 300]
        t = Table(data_pairs, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        return t

    def generate_report(self, output_pdf_path):
        doc = SimpleDocTemplate(output_pdf_path, pagesize=A4,
                               leftMargin=20*mm, rightMargin=20*mm,
                               topMargin=15*mm, bottomMargin=15*mm)
        styles = getSampleStyleSheet()
        story = []

        # Custom styles
        normal_style = styles['Normal']
        small_style = ParagraphStyle('Small', parent=normal_style, fontSize=8)

        # =====================================================================
        # TITLE PAGE
        # =====================================================================
        title_style = ParagraphStyle('MainTitle', parent=styles['Heading1'],
                                      fontSize=24, spaceAfter=20, alignment=1)
        story.append(Spacer(1, 50))
        story.append(Paragraph("Manufacturing Analysis Report", title_style))
        story.append(Spacer(1, 20))

        subtitle_style = ParagraphStyle('Subtitle', parent=styles['Heading2'],
                                         fontSize=16, alignment=1, textColor=colors.grey)
        story.append(Paragraph(f"{self.data.get('part_name', 'Unknown Part')}", subtitle_style))
        story.append(Spacer(1, 30))

        # Quick summary box
        is_turned = "Yes" if self.data.get('is_turned_part') else "No"
        geom = self.data.get('geometric_properties', {})
        mfg = self.data.get('manufacturing_analysis', {})

        summary_data = [
            ['Total Holes:', str(len(self.data.get('holes', [])))],
            ['Turned Part:', is_turned],
            ['Volume:', f"{geom.get('volume', 0):,.0f} mm³"],
            ['Surface Area:', f"{geom.get('surface_area', 0):,.0f} mm²"],
        ]

        if mfg:
            iso_rec = mfg.get('iso2768', {})
            if iso_rec:
                summary_data.append(['ISO 2768:', iso_rec.get('designation', 'N/A')])

            mass_est = mfg.get('mass_estimates', {})
            steel_mass = mass_est.get('steel_s235', {})
            if steel_mass:
                summary_data.append(['Est. Mass (Steel):', f"{steel_mass.get('mass_kg', 0):.2f} kg"])

        summary_table = Table(summary_data, colWidths=[120, 150])
        summary_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.darkblue),
            ('BACKGROUND', (0, 0), (0, -1), colors.Color(0.95, 0.95, 1.0)),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 20))

        # Standards reference
        story.append(Paragraph("<b>Applicable Standards:</b>", normal_style))
        standards_list = [
            "ISO 2768 - General tolerances",
            "ISO 286 - Limits and fits",
            "ISO 1302 - Surface texture",
            "ISO 68-1 / ISO 261 - Metric screw threads",
            "ISO 13715 - Edge conditions",
            "EN 10025 / EN 573 - Material specifications",
        ]
        for std in standards_list:
            story.append(Paragraph(f"  • {std}", small_style))

        story.append(PageBreak())

        # =====================================================================
        # SECTION 1: ISO 2768 TOLERANCES
        # =====================================================================
        if mfg and mfg.get('iso2768'):
            story.append(self._create_section_header("ISO 2768 - General Tolerances", styles))

            iso_data = mfg['iso2768']
            story.append(Paragraph(f"<b>Recommended Designation:</b> {iso_data.get('designation', 'N/A')}", normal_style))
            story.append(Paragraph(f"<b>Linear Tolerance Class:</b> {iso_data.get('linear_class', 'N/A').upper()} "
                                   f"(f=fine, m=medium, c=coarse, v=very coarse)", small_style))
            story.append(Paragraph(f"<b>Geometric Tolerance Class:</b> {iso_data.get('geometric_class', 'N/A')} "
                                   f"(H=precise, K=standard, L=relaxed)", small_style))
            story.append(Spacer(1, 8))

            # Tolerance table
            tol_table = iso_data.get('tolerance_table', [])
            if tol_table:
                story.append(Paragraph("<b>Dimension Tolerances:</b>", normal_style))
                tol_data = [['Dimension (mm)', 'Tolerance', 'Class']]
                for t in tol_table:
                    tol_data.append([f"{t['dimension']:.1f}", t['tolerance'], t['class'].upper()])

                t_tol = Table(tol_data, colWidths=[100, 80, 60])
                t_tol.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.3, 0.5)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                story.append(t_tol)
            story.append(Spacer(1, 12))

        # =====================================================================
        # SECTION 2: ISO 286 FITS & TOLERANCES
        # =====================================================================
        if mfg and mfg.get('holes_with_fits'):
            story.append(self._create_section_header("ISO 286 - Hole Fits & Tolerances", styles))

            holes_fits = mfg['holes_with_fits']
            fit_data = [['Diameter', 'Count', 'Recommended Fit', 'Fit Type', 'H7 Tolerance']]

            for h in holes_fits[:15]:  # Limit to 15 rows
                fit = h.get('fit_recommendation', {})
                fit_data.append([
                    f"Ø{h['diameter']:.1f} mm",
                    str(h['count']),
                    fit.get('fit', 'N/A'),
                    fit.get('type', 'N/A'),
                    h.get('tolerances', {}).get('H7', 'N/A'),
                ])

            t_fits = Table(fit_data, colWidths=[70, 45, 90, 70, 80])
            t_fits.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.1, 0.4, 0.3)),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.98, 0.95)]),
            ]))
            story.append(t_fits)

            if len(holes_fits) > 15:
                story.append(Paragraph(f"<i>... and {len(holes_fits) - 15} more hole sizes</i>", small_style))
            story.append(Spacer(1, 12))

        # =====================================================================
        # SECTION 3: ISO 68-1 THREAD DETECTION
        # =====================================================================
        if mfg and mfg.get('threads'):
            story.append(self._create_section_header("ISO 68-1 / ISO 261 - Metric Thread Detection", styles))

            threads = mfg['threads']
            thread_summary = threads.get('summary', {})

            if thread_summary:
                story.append(Paragraph(f"<b>Detected {len(threads.get('detected', []))} potential threaded holes</b>", normal_style))
                story.append(Spacer(1, 6))

                thread_data = [['Thread', 'Count', 'Tap Drill (mm)', 'Pitch (mm)']]
                detected = threads.get('detected', [])

                # Group by designation
                thread_groups = {}
                for t in detected:
                    des = t['thread_designation']
                    if des not in thread_groups:
                        thread_groups[des] = {'count': 0, 'pitch': t['pitch'], 'tap_drill': t['tap_drill']}
                    thread_groups[des]['count'] += 1

                for des, info in sorted(thread_groups.items()):
                    thread_data.append([
                        des,
                        str(info['count']),
                        f"{info['tap_drill']:.2f}" if info['tap_drill'] else "N/A",
                        f"{info['pitch']:.2f}",
                    ])

                t_threads = Table(thread_data, colWidths=[80, 60, 80, 70])
                t_threads.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.4, 0.2, 0.4)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                story.append(t_threads)
            else:
                story.append(Paragraph("No standard metric threads detected.", normal_style))
            story.append(Spacer(1, 12))

        # =====================================================================
        # SECTION 4: ISO 1302 SURFACE FINISH
        # =====================================================================
        if mfg and mfg.get('surface_finish'):
            story.append(self._create_section_header("ISO 1302 - Surface Finish Requirements", styles))

            sf = mfg['surface_finish']
            story.append(Paragraph(f"<b>Default Surface Roughness:</b> Ra {sf.get('default_ra', 3.2)} μm", normal_style))
            story.append(Paragraph(f"<b>Recommendation:</b> {sf.get('general_recommendation', 'N/A')}", normal_style))
            story.append(Spacer(1, 8))

            by_face = sf.get('by_face_type', [])
            if by_face:
                sf_data = [['Face Type', 'Count', '%', 'Ra (μm)', 'Process']]
                for face in by_face[:8]:
                    sf_data.append([
                        face['face_type'],
                        str(face['count']),
                        f"{face['percentage']:.1f}%",
                        str(face['recommended_ra']),
                        face['typical_process'],
                    ])

                t_sf = Table(sf_data, colWidths=[70, 50, 40, 50, 120])
                t_sf.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.3, 0.3, 0.5)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                story.append(t_sf)
            story.append(Spacer(1, 12))

        # =====================================================================
        # SECTION 5: ISO 13715 EDGE CONDITIONS
        # =====================================================================
        if mfg and mfg.get('edges'):
            story.append(self._create_section_header("ISO 13715 - Edge Conditions (Chamfers & Fillets)", styles))

            edges = mfg['edges']
            chamfers = edges.get('chamfers', {})
            fillets = edges.get('fillets', {})

            edge_info = [
                ['Feature', 'Count', 'Average Size', 'Recommended Standard'],
                ['Chamfers', str(chamfers.get('count', 0)),
                 f"{chamfers.get('average_size', 0):.2f} mm",
                 f"{chamfers.get('recommended_standard', 1.0)}×45°"],
                ['Fillets', str(fillets.get('count', 0)),
                 f"R{fillets.get('average_radius', 0):.2f} mm",
                 f"R{fillets.get('recommended_standard', 2.0)}"],
            ]

            t_edges = Table(edge_info, colWidths=[70, 50, 80, 120])
            t_edges.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.4, 0.3, 0.2)),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(t_edges)
            story.append(Spacer(1, 6))
            story.append(Paragraph(f"<i>Note: {edges.get('edge_note', '')}</i>", small_style))
            story.append(Spacer(1, 12))

        # =====================================================================
        # SECTION 6: MATERIAL & MASS ESTIMATION
        # =====================================================================
        if mfg and mfg.get('mass_estimates'):
            story.append(self._create_section_header("EN 10025/573 - Material & Mass Estimation", styles))

            mass_est = mfg['mass_estimates']
            mass_data = [['Material', 'Standard', 'Density (kg/m³)', 'Mass (kg)']]

            for key, data in mass_est.items():
                if data:
                    mass_data.append([
                        data.get('material', key),
                        data.get('standard', 'N/A'),
                        str(data.get('density_kg_m3', 'N/A')),
                        f"{data.get('mass_kg', 0):.3f}",
                    ])

            if len(mass_data) > 1:
                t_mass = Table(mass_data, colWidths=[120, 80, 80, 70])
                t_mass.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.5, 0.3, 0.1)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                story.append(t_mass)
            story.append(Spacer(1, 12))

        # =====================================================================
        # SECTION 7: MANUFACTURING PROCESS RECOMMENDATION
        # =====================================================================
        if mfg and mfg.get('manufacturing_process'):
            story.append(self._create_section_header("Manufacturing Process Recommendation", styles))

            proc = mfg['manufacturing_process']
            story.append(Paragraph(f"<b>Primary Process:</b> {proc.get('primary', 'N/A')}", normal_style))
            story.append(Paragraph(f"<b>Complexity:</b> {proc.get('complexity', 'N/A').upper()}", normal_style))
            story.append(Spacer(1, 6))

            secondary = proc.get('secondary', [])
            if secondary:
                story.append(Paragraph("<b>Secondary Operations:</b>", normal_style))
                for op in secondary:
                    story.append(Paragraph(f"  • {op}", small_style))
            story.append(Spacer(1, 12))

        story.append(PageBreak())

        # =====================================================================
        # SECTION 8: WERKVOORBEREIDING (Manufacturing Preparation)
        # =====================================================================
        wv = mfg.get('werkvoorbereiding') if mfg else None
        if wv:
            story.append(self._create_section_header("Werkvoorbereiding / Manufacturing Preparation", styles))
            story.append(Spacer(1, 6))

            # Cost Estimation
            cost = wv.get('cost_estimate', {})
            if cost:
                story.append(Paragraph("<b>Kostprijsberekening / Cost Estimate</b>", normal_style))
                cost_data = [
                    ['Item', 'Bedrag'],
                    ['Kostprijs per stuk', f"€{cost.get('cost_per_piece', 0):.2f}"],
                    ['Materiaalkosten', f"€{cost.get('breakdown', {}).get('material', 0):.2f}"],
                    ['Bewerkingskosten', f"€{cost.get('breakdown', {}).get('machining', 0):.2f}"],
                    ['Setup per stuk', f"€{cost.get('breakdown', {}).get('setup_per_piece', 0):.2f}"],
                ]
                time_est = cost.get('time_estimate', {})
                if time_est:
                    cost_data.append(['Bewerkingstijd', f"{time_est.get('total_time_hours', 0):.2f} uur"])
                cost_data.append(['Uurtarief', f"€{cost.get('hourly_rate', 0):.2f}/uur"])

                t_cost = Table(cost_data, colWidths=[150, 100])
                t_cost.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.4, 0.3)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                story.append(t_cost)
                story.append(Spacer(1, 12))

            # Tool List
            tools = wv.get('tool_list', [])
            if tools:
                story.append(Paragraph("<b>Gereedschapslijst / Tool List</b>", normal_style))
                tool_data = [['Gereedschap', 'Ø (mm)', 'Kosten']]
                for tool in tools[:10]:
                    tool_data.append([
                        tool.get('designation', ''),
                        f"{tool.get('diameter', 0):.1f}",
                        f"€{tool.get('estimated_cost', 0):.2f}",
                    ])
                if len(tools) > 10:
                    tool_data.append(['...', f'+{len(tools)-10}', ''])

                t_tools = Table(tool_data, colWidths=[180, 50, 60])
                t_tools.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.3, 0.3, 0.4)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                story.append(t_tools)
                story.append(Spacer(1, 12))

            # Outsourcing
            outsource = wv.get('outsourcing', {})
            if outsource:
                story.append(Paragraph("<b>Uitbesteding / Outsourcing</b>", normal_style))
                story.append(Paragraph(f"Categorie: <b>{outsource.get('primary_category', 'N/A')}</b>", normal_style))
                story.append(Paragraph(f"Doorlooptijd: {outsource.get('estimated_lead_time_days', 0)} werkdagen", small_style))
                story.append(Paragraph(f"Aanbeveling: {outsource.get('recommendation', '')}", small_style))

                routing = outsource.get('routing', [])
                if routing:
                    story.append(Spacer(1, 4))
                    story.append(Paragraph("<i>Routing:</i>", small_style))
                    for r in routing:
                        story.append(Paragraph(f"  {r.get('step', 0)}. {r.get('description', '')}", small_style))
                story.append(Spacer(1, 12))

            # Surface Treatment Options
            treatments = wv.get('surface_treatment_options', [])
            if treatments and isinstance(treatments, list) and len(treatments) > 0:
                if isinstance(treatments[0], dict) and 'warning' not in treatments[0]:
                    story.append(Paragraph("<b>Oppervlaktebehandeling Opties</b>", normal_style))
                    treat_data = [['Behandeling', 'Standaard', 'Dikte', 'Kosten']]
                    for t in treatments[:5]:
                        treat_data.append([
                            t.get('name', ''),
                            t.get('standard', ''),
                            t.get('thickness', ''),
                            f"×{t.get('cost_factor', 1.0):.1f}",
                        ])

                    t_treat = Table(treat_data, colWidths=[120, 70, 60, 45])
                    t_treat.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.4, 0.3, 0.5)),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ]))
                    story.append(t_treat)
                    story.append(Spacer(1, 12))

            # Purchase Specification
            purchase = wv.get('purchase_specification', {})
            if purchase:
                story.append(Paragraph("<b>Inkoop Specificatie / Purchase Spec</b>", normal_style))
                mat = purchase.get('material', {})
                raw = purchase.get('raw_material', {})
                story.append(Paragraph(f"Materiaal: <b>{mat.get('name', 'N/A')}</b> ({mat.get('standard', '')})", normal_style))
                story.append(Paragraph(f"Ruw formaat: {raw.get('dimensions', 'N/A')} ({raw.get('form', '')})", small_style))
                story.append(Paragraph(f"Ruw gewicht: {raw.get('mass_per_piece_kg', 0):.2f} kg/stuk", small_style))
                story.append(Paragraph(f"Certificaat: {purchase.get('certification', 'N/A')}", small_style))

                est_cost = purchase.get('estimated_cost', {})
                if est_cost:
                    story.append(Paragraph(f"Materiaalprijs: €{est_cost.get('per_kg', 0):.2f}/kg → €{est_cost.get('per_piece', 0):.2f}/stuk", small_style))
                story.append(Spacer(1, 12))

        story.append(PageBreak())

        # =====================================================================
        # EXISTING SECTIONS (Updated)
        # =====================================================================

        # Topology Statistics
        topo = self.data.get('topology_stats')
        if topo:
            story.append(self._create_section_header("Topology Statistics", styles))
            topo_data = [
                ['Entity', 'Count'],
                ['Solids', str(topo.get('solids', 0))],
                ['Shells', str(topo.get('shells', 0))],
                ['Faces', str(topo.get('faces', 0))],
                ['Edges', str(topo.get('edges', 0))],
                ['Vertices', str(topo.get('vertices', 0))],
            ]
            t_topo = Table(topo_data, colWidths=[100, 80])
            t_topo.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(t_topo)
            story.append(Spacer(1, 12))

        # Component Classification
        comps = self.data.get('component_classification')
        if comps:
            story.append(self._create_section_header("Component Classification", styles))
            story.append(Spacer(1, 6))

            # Add Pie Chart
            pie_chart = self._create_pie_chart(comps)
            if pie_chart:
                story.append(pie_chart)
                story.append(Spacer(1, 12))

            comp_data = [['Component Type', 'Count']]
            for ctype, count in comps.items():
                if count > 0:
                    comp_data.append([ctype, str(count)])

            t_comps = Table(comp_data, colWidths=[180, 80])
            t_comps.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            story.append(t_comps)
            story.append(Spacer(1, 12))

        # Face Analysis
        faces = self.data.get('face_analysis')
        if faces:
            story.append(self._create_section_header("Surface Complexity Analysis", styles))
            story.append(Spacer(1, 6))

            # Add Bar Chart
            bar_chart = self._create_bar_chart(faces)
            if bar_chart:
                story.append(bar_chart)
                story.append(Spacer(1, 12))

            face_data = [['Surface Type', 'Count']]
            for ftype, count in faces.items():
                if count > 0:
                    face_data.append([ftype, str(count)])

            t_faces = Table(face_data, colWidths=[120, 80])
            t_faces.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            story.append(t_faces)
            story.append(Spacer(1, 12))

        story.append(PageBreak())

        # Detailed Part Analysis
        detailed_parts = self.data.get('detailed_parts')
        if detailed_parts:
            story.append(self._create_section_header("Detailed Part Analysis (Grouped)", styles))
            story.append(Spacer(1, 12))

            for part in detailed_parts[:20]:  # Limit to 20 parts
                # Prepare data for the table
                img_path = part.get('image_path')
                img_obj = Paragraph("No Image", normal_style)

                if img_path and os.path.exists(img_path):
                    try:
                        drawing = svg2rlg(img_path)
                        drawing.scale(0.6, 0.6)
                        img_obj = drawing
                    except Exception as e:
                        print(f"Error loading SVG {img_path}: {e}")

                # Part Data
                dims = part.get('dimensions', [0, 0, 0])
                sm = part.get('sheet_metal', {})
                mfg_part = part.get('manufacturing', {})

                p_data = [
                    [Paragraph(f"<b>Part ID:</b> {part.get('id')}", normal_style)],
                    [Paragraph(f"<b>Count:</b> {part.get('count')}", normal_style)],
                    [Paragraph(f"<b>Type:</b> {part.get('classification')}", normal_style)],
                    [Paragraph(f"<b>Dims:</b> {dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm", normal_style)],
                    [Paragraph(f"<b>Vol:</b> {part.get('volume', 0):.1f} mm³", normal_style)],
                    [Paragraph(f"<b>Holes:</b> {part.get('hole_summary', 'None')}", small_style)]
                ]

                if sm.get('is_sheet_metal'):
                    std_str = " (ISO Std)" if sm.get('is_standard') else ""
                    p_data.append([Paragraph(f"<b>Sheet:</b> {sm.get('thickness')}mm{std_str}, {sm.get('bend_count')} bends", normal_style)])

                # Per-part ISO Manufacturing Data
                if mfg_part:
                    # Mass estimates
                    mass_est = mfg_part.get('mass_estimates', {})
                    if mass_est:
                        steel_kg = mass_est.get('steel_s235', 0)
                        alu_kg = mass_est.get('alu_6061', 0)
                        if steel_kg > 0.001:
                            p_data.append([Paragraph(f"<b>Mass:</b> {steel_kg:.3f}kg (steel) / {alu_kg:.3f}kg (alu)", small_style)])

                    # Holes with fits (ISO 286)
                    holes_fits = mfg_part.get('holes_with_fits', [])
                    if holes_fits:
                        fit_strs = []
                        for hf in holes_fits[:3]:
                            fit = hf.get('fit_recommendation', {})
                            fit_strs.append(f"Ø{hf['diameter']}:{fit.get('fit', 'N/A')}")
                        if len(holes_fits) > 3:
                            fit_strs.append(f"+{len(holes_fits)-3} more")
                        p_data.append([Paragraph(f"<b>Fits:</b> {', '.join(fit_strs)}", small_style)])

                    # Threads (ISO 68-1)
                    threads = mfg_part.get('threads', [])
                    if threads:
                        thread_strs = [f"{t['count']}×{t['thread_designation']}" for t in threads[:3]]
                        p_data.append([Paragraph(f"<b>Threads:</b> {', '.join(thread_strs)}", small_style)])

                    # Chamfers/Fillets (ISO 13715)
                    cf = mfg_part.get('chamfers_fillets', {})
                    if cf and (cf.get('chamfer_count', 0) > 0 or cf.get('fillet_count', 0) > 0):
                        cf_str = f"{cf.get('chamfer_count', 0)} chamfers, {cf.get('fillet_count', 0)} fillets"
                        p_data.append([Paragraph(f"<b>Edges:</b> {cf_str}", small_style)])

                # Create a nested table for data
                t_data = Table(p_data, colWidths=[200])
                t_data.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))

                # Main row table
                row_data = [[img_obj, t_data]]
                t_row = Table(row_data, colWidths=[130, 220])
                t_row.setStyle(TableStyle([
                    ('BOX', (0, 0), (-1, -1), 1, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('PADDING', (0, 0), (-1, -1), 6),
                ]))

                story.append(KeepTogether(t_row))
                story.append(Spacer(1, 4))

            if len(detailed_parts) > 20:
                story.append(Paragraph(f"<i>... and {len(detailed_parts) - 20} more unique parts</i>", small_style))

        story.append(PageBreak())

        # Hole Summary
        story.append(self._create_section_header("Hole Summary by Diameter", styles))
        story.append(Spacer(1, 6))

        holes = self.data.get('holes', [])
        if holes:
            diameters = [h['diameter'] for h in holes]
            diameter_counts = Counter(diameters)

            table_data = [['Diameter (mm)', 'Count']]
            for dia, count in sorted(diameter_counts.items()):
                table_data.append([f"{dia:.2f}", str(count)])

            t = Table(table_data, colWidths=[100, 80])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            story.append(t)
        else:
            story.append(Paragraph("No holes detected.", normal_style))

        # Footer
        story.append(Spacer(1, 30))
        story.append(Paragraph("─" * 60, normal_style))
        story.append(Paragraph("<i>Report generated by Manufacturing Pipeline - Dutch/ISO Standards Analysis</i>", small_style))

        doc.build(story)
        print(f"PDF Report generated: {output_pdf_path}")

if __name__ == "__main__":
    # Test with the existing JSON file
    json_file = "core_one_assembly_results.json"
    if os.path.exists(json_file):
        generator = PDFReportGenerator(json_file)
        generator.generate_report("core_one_assembly_report.pdf")
    else:
        print(f"File {json_file} not found.")
