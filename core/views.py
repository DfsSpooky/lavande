# laundry_app/core/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.urls import reverse

# Primero, importamos todos los MODELOS desde models.py
from .models import Customer, Order, Category, OrderCategory, AppConfiguration, Product, Sale, SaleItem, ProductCategory
# Segundo, importamos todos los FORMULARIOS desde forms.py
from .forms import (
    CustomerForm, OrderForm, CategoryForm, OrderCategoryInlineForm, 
    CustomerFilterForm, OrderFilterForm, ReceiveOrderForm, ConfigurationForm,
    ProductForm, SaleItemForm, ReportFilterForm, OrderEditForm,
    SaleForm  # <-- Incluyendo el SaleForm que creamos
)

from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger # Importa PageNotAnInteger y EmptyPage
from django.db.models import Q, ProtectedError, Sum, F, ExpressionWrapper, DecimalField, Case, When, Value, BooleanField, Max
from django.db.models.functions import Coalesce
from datetime import date, datetime, timedelta # Importa date y datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO
from decimal import Decimal
import os
from django.db import transaction
import csv
from django.db.models import Count
from .forms import ReportFilterForm
import json
from django.db import transaction
from decimal import Decimal
from urllib.parse import quote


def home(request):
    return render(request, 'core/home.html')

@login_required
def dashboard(request):
    """
    Muestra un dashboard completo con filtros, paginación y estadísticas optimizadas.

    Esta vista combina la funcionalidad original del dashboard del usuario con
    consultas a la base de datos mucho más eficientes para calcular los ingresos,
    evitando bucles en Python y delegando el trabajo a la base de datos.
    """
    # 1. Inicializa los formularios de filtro con los datos GET
    customer_filter_form = CustomerFilterForm(request.GET)
    order_filter_form = OrderFilterForm(request.GET)

    # 2. Lógica de Resumen de Ingresos (OPTIMIZADA)
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    # Optimizamos el cálculo de ingresos usando agregaciones de la base de datos.
    # Esto es mucho más rápido que iterar en Python.
    income_base_query = Order.objects.filter(payment_status__in=['PAID', 'PARTIAL']
    ).exclude(status='CANCELLED')
    daily_income = income_base_query.filter(created_at__date=today).aggregate(
        total=Coalesce(Sum(F('original_calculated_price') - F('discount_amount')), Decimal('0.0'), output_field=DecimalField())
    )['total']

    weekly_income = income_base_query.filter(created_at__date__gte=start_of_week).aggregate(
        total=Coalesce(Sum(F('original_calculated_price') - F('discount_amount')), Decimal('0.0'), output_field=DecimalField())
    )['total']

    monthly_income = income_base_query.filter(created_at__date__gte=start_of_month).aggregate(
        total=Coalesce(Sum(F('original_calculated_price') - F('discount_amount')), Decimal('0.0'), output_field=DecimalField())
    )['total']

    # 3. Contadores Rápidos de Órdenes por Estado (Corregido)
    orders_processing_count = Order.objects.filter(status='PROCESSING').count()
    # Corregido: 'COMPLETED' no existe, el estado correcto es 'READY' según tu modelo.
    orders_ready_count = Order.objects.filter(status='READY').count()
    orders_payment_pending_count = Order.objects.filter(payment_status__in=['PENDING', 'PARTIAL']).count()
    orders_total_count = Order.objects.count()

    # 4. Lógica de Clientes (Búsqueda y Paginación) - Sin cambios, funciona bien
    customer_list = Customer.objects.all().order_by('name')
    if customer_filter_form.is_valid():
        search_query = customer_filter_form.cleaned_data.get('search_query')
        if search_query:
            customer_list = customer_list.filter(
                Q(name__icontains=search_query) |
                Q(customer_code__icontains=search_query) |
                Q(phone__icontains=search_query)
            )
    
    total_customers = customer_list.count()
    paginator_customers = Paginator(customer_list, 10)
    page_customers = request.GET.get('page_customers')
    try:
        customers_page = paginator_customers.page(page_customers)
    except PageNotAnInteger:
        customers_page = paginator_customers.page(1)
    except EmptyPage:
        customers_page = paginator_customers.page(paginator_customers.num_pages)
        
    # --- INICIO DE NUEVA IMPLEMENTACIÓN ---
    # 5. Top 5 Clientes por Gasto Total (CORREGIDO)
    top_customers = Customer.objects.annotate(
        total_spent=Coalesce(Sum(
            (F('order__original_calculated_price') - F('order__discount_amount')),
            # --- CORRECCIÓN APLICADA AQUÍ ---
            filter=~Q(order__status='CANCELLED')
        ), Decimal('0.0'), output_field=DecimalField())
    ).order_by('-total_spent')[:5]

    # 6. Pedidos que Requieren Atención (en proceso por más de 3 días)
    attention_threshold_date = date.today() - timedelta(days=3)
    attention_orders = Order.objects.filter(
        status='PROCESSING',
        created_at__date__lte=attention_threshold_date
    ).order_by('created_at')
    # --- FIN DE NUEVA IMPLEMENTACIÓN ---


    # 7. Lógica de Pedidos (Filtro y Paginación) - Sin cambios, funciona bien
    order_list = Order.objects.select_related('customer').all().order_by('-created_at')
    if order_filter_form.is_valid():
        status = order_filter_form.cleaned_data.get('status')
        payment_status = order_filter_form.cleaned_data.get('payment_status')
        date_from = order_filter_form.cleaned_data.get('date_from')
        date_to = order_filter_form.cleaned_data.get('date_to')

        if status:
            order_list = order_list.filter(status=status)
        if payment_status:
            order_list = order_list.filter(payment_status=payment_status)
        if date_from:
            order_list = order_list.filter(created_at__date__gte=date_from)
        if date_to:
            order_list = order_list.filter(created_at__date__lte=date_to)

    paginator_orders = Paginator(order_list, 10)
    orders_page_number = request.GET.get('page_orders')
    try:
        orders_page = paginator_orders.page(orders_page_number)
    except PageNotAnInteger:
        orders_page = paginator_orders.page(1)
    except EmptyPage:
        orders_page = paginator_orders.page(paginator_orders.num_pages)

    # 8. Contexto final para el template (coincide con tu HTML y añade lo nuevo)
    context = {
        'orders': orders_page,
        'customers': customers_page,
        'daily_income': daily_income,
        'weekly_income': weekly_income,
        'monthly_income': monthly_income,
        'customer_filter_form': customer_filter_form,
        'order_filter_form': order_filter_form,
        'orders_processing_count': orders_processing_count,
        'orders_completed_count': orders_ready_count,  # Nombre de variable que usa tu HTML
        'orders_payment_pending_count': orders_payment_pending_count,
        'orders_total_count': orders_total_count,
        'total_customers': total_customers,
        'top_customers': top_customers, # Nueva variable
        'attention_orders': attention_orders, # Nueva variable
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def add_customer(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            messages.success(request, f'Cliente {customer.name} agregado correctamente con código {customer.customer_code}.')
            return redirect('dashboard')
    else:
        form = CustomerForm()
    return render(request, 'core/add_customer.html', {'form': form})

@login_required
def add_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoría agregada correctamente.')
            return redirect('dashboard')
    else:
        form = CategoryForm()
    return render(request, 'core/add_category.html', {'form': form})

@login_required
def add_order(request):
    """
    Paso 1 del flujo: Crea el pedido con los datos básicos.
    Responde con JSON para una experiencia de usuario sin recargas de página.
    """
    OrderCategoryFormSet = formset_factory(OrderCategoryInlineForm, extra=1, min_num=0, validate_min=False)
    
    if request.method == 'POST':
        order_form = OrderForm(request.POST)
        formset = OrderCategoryFormSet(request.POST, prefix='formset')

        if order_form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    final_price_override_str = request.POST.get('final_price_override', '').strip()
                    
                    # --- CORRECCIÓN ---
                    # Obtenemos el precio por kilo desde la configuración de forma segura
                    try:
                        price_setting = AppConfiguration.objects.get(key='default_price_per_kg')
                        price_per_kg = Decimal(price_setting.value)
                    except (AppConfiguration.DoesNotExist, ValueError):
                        # Si no se encuentra la configuración, usamos un valor por defecto seguro.
                        price_per_kg = Decimal('5.00')

                    order = order_form.save(commit=False)
                    # Nos aseguramos de asignar el precio por kilo correcto al pedido
                    order.weight_price_per_kg = price_per_kg
                    order.total_weight = order.weight if order.weight is not None else Decimal('0.00')
                    order.payment_status = 'PENDING'
                    order.save()

                    initial_price = Decimal('0.00')
                    if order.weight: 
                        initial_price += Decimal(order.weight) * price_per_kg
                    
                    for form in formset:
                        # Se procesa el formulario solo si tiene datos y es válido
                        if form.has_changed() and form.is_valid() and not form.cleaned_data.get('DELETE', False):
                            category = form.cleaned_data.get('category')
                            quantity = form.cleaned_data.get('quantity')
                            if category and quantity and quantity > 0:
                                OrderCategory.objects.create(order=order, category=category, quantity=quantity)
                                initial_price += Decimal(category.price) * Decimal(quantity)
                    
                    order.original_calculated_price = initial_price.quantize(Decimal('0.01'))

                    if final_price_override_str:
                        final_price = Decimal(final_price_override_str)
                        if final_price != initial_price:
                            order.price_adjusted_by_user = True
                            order.discount_amount = (initial_price - final_price).quantize(Decimal('0.01'))
                    
                    order.save()
                    order.generate_qr_code()
                    
                    return JsonResponse({
                        'success': True, 'order_id': order.id, 'order_code': order.order_code,
                        'total_price': order.total_price,
                    })
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)})
        else:
            # Errores de validación (mejorado para ser más descriptivo)
            error_list = {f'campo_{field}': error[0] for field, error in order_form.errors.items()}
            for i, form_errors in enumerate(formset.errors):
                if form_errors:
                    for field, error in form_errors.items():
                        error_list[f'articulo_{i+1}_{field}'] = error[0]
            return JsonResponse({'success': False, 'error': 'Por favor, corrige los errores.', 'details': error_list})
    
    # Para peticiones GET, prepara el formulario y lo muestra
    order_form = OrderForm()
    formset = OrderCategoryFormSet(prefix='formset')
    categories = Category.objects.all().values('id', 'price')
    category_prices = {str(cat['id']): str(cat['price']) for cat in categories}
    
    context = {
        'order_form': order_form, 'formset': formset,
        'category_prices_json': json.dumps(category_prices),
    }
    return render(request, 'core/add_order.html', context)

@login_required
def register_payment(request, order_id):
    """
    Paso 2 del flujo: Recibe los datos de pago desde el modal y actualiza el pedido.
    """
    if request.method == 'POST':
        try:
            order = Order.objects.get(id=order_id)
            order.payment_status = request.POST.get('payment_status')
            order.payment_method = request.POST.get('payment_method')
            
            partial_amount_str = request.POST.get('partial_amount', '0').strip()
            if order.payment_status == 'PARTIAL' and partial_amount_str:
                order.partial_amount = Decimal(partial_amount_str)
            else:
                order.partial_amount = Decimal('0.00')

            if 'payment_proof' in request.FILES:
                order.payment_proof = request.FILES['payment_proof']
                
            order.save()
            return JsonResponse({'success': True, 'order_code': order.order_code})
        except Order.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Pedido no encontrado.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Método no permitido.'})

def order_status(request, short_id):
    """
    Muestra la página pública con el estado de un pedido, buscándolo por su
    'short_id' que es corto, único y seguro.
    """
    try:
        # Buscamos el pedido usando el nuevo campo 'short_id' que viene de la URL.
        order = Order.objects.get(short_id=short_id)
        context = {
            'order': order,
        }
        return render(request, 'core/order_status.html', context)
    except Order.DoesNotExist:
        # Si alguien inventa un código que no existe, le mostramos un error.
        return render(request, 'core/order_not_found.html')

@login_required
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        order.status = 'READY'
        order.save()
        messages.success(request, f'Pedido {order.id} marcado como listo para recoger.')
        return redirect('dashboard')
    return redirect('dashboard')

@login_required
def update_payment_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        payment_status = request.POST.get('payment_status')
        partial_amount = request.POST.get('partial_amount')
        payment_proof = request.FILES.get('payment_proof')
        if payment_status in ['PENDING', 'PAID', 'PARTIAL']:
            order.payment_status = payment_status
            if payment_status == 'PARTIAL' and partial_amount:
                try:
                    order.partial_amount = float(partial_amount)
                except ValueError:
                    messages.error(request, 'Monto parcial inválido.')
                    return redirect('dashboard')
            if payment_proof:
                order.payment_proof = payment_proof
            order.save()
            messages.success(request, f'Estado de pago del pedido {order.id} actualizado correctamente.')
        else:
            messages.error(request, 'Estado de pago inválido.')
        return redirect('dashboard')
    return redirect('dashboard')

@login_required
def manage_customer_orders(request, customer_code):
    customer = get_object_or_404(Customer, customer_code=customer_code)
    orders = Order.objects.filter(customer=customer).order_by('-created_at')

    # Calculamos la deuda total sumando los montos restantes de cada pedido de este cliente
    customer_total_due = sum(order.remaining_amount() for order in orders)

    # Creamos el contexto y añadimos la nueva variable
    context = {
        'customer': customer, 
        'orders': orders,
        'customer_total_due': customer_total_due, # <-- La nueva variable que necesita el HTML
    }
    
    return render(request, 'core/manage_customer_orders.html', context)

def customer_status(request, customer_code):
    customer = get_object_or_404(Customer, customer_code=customer_code)
    orders = Order.objects.filter(customer=customer).order_by('-created_at')
    return render(request, 'core/customer_status.html', {'customer': customer, 'orders': orders})

@login_required
def edit_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    OrderCategoryFormSet = formset_factory(OrderCategoryInlineForm, extra=1, can_delete=True)

    if request.method == 'POST':
        order_form = OrderEditForm(request.POST, request.FILES, instance=order)
        formset = OrderCategoryFormSet(request.POST, prefix='formset')

        if order_form.is_valid() and formset.is_valid():
            order = order_form.save(commit=False)
            order.customer = get_object_or_404(Customer, id=order.customer_id)

            OrderCategory.objects.filter(order=order).delete()
            initial_price = Decimal('0.00')
            if order.weight:
                initial_price += Decimal(order.weight) * order.weight_price_per_kg

            for form in formset:
                if not form.cleaned_data.get('DELETE', False) and form.has_changed():
                    category = form.cleaned_data.get('category')
                    quantity = form.cleaned_data.get('quantity')
                    if category and quantity and quantity > 0:
                        OrderCategory.objects.create(order=order, category=category, quantity=quantity)
                        initial_price += Decimal(category.price) * Decimal(quantity)

            order.original_calculated_price = initial_price
            order.price_adjusted_by_user = True

            if order.payment_status == 'PAID':
                order.partial_amount = order.total_price
            elif order.payment_status == 'PENDING':
                order.partial_amount = 0

            order.save()

            messages.success(request, f'Pedido #{order.order_code} actualizado correctamente.')
            return redirect('manage_customer_orders', customer_code=order.customer.customer_code)
        else:
            messages.error(request, 'Hubo un error al guardar el pedido. Por favor, revisa los campos.')

    else: # GET request
        order_form = OrderEditForm(instance=order)
        initial_formset_data = [{'category': oc.category_id, 'quantity': oc.quantity} for oc in order.ordercategory_set.all()]
        formset = OrderCategoryFormSet(initial=initial_formset_data, prefix='formset')

    categories = Category.objects.all().values('id', 'price')
    category_prices = {str(cat['id']): str(cat['price']) for cat in categories}

    context = {
        'order_form': order_form,
        'formset': formset,
        'order': order,
        'category_prices_json': json.dumps(category_prices)
    }
    # --- RUTA CORREGIDA ---
    # Django ya sabe que debe buscar en la carpeta 'templates' de la app.
    return render(request, 'core/edit_order.html', context)




@login_required
def download_order_pdf(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesizes=letter,
                            rightMargin=0.75 * inch, leftMargin=0.75 * inch,
                            topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    elements = []

    # --- Modern Color Palette & Fonts ---
    # Using a slightly darker primary color for a more corporate feel
    primary_color = colors.HexColor('#1A73E8') # A common blue in modern tech UIs
    secondary_color = colors.HexColor('#E8F0FE') # Very light blue for subtle backgrounds
    text_dark = colors.HexColor('#202124') # Near black for primary text
    text_medium = colors.HexColor('#5F6368') # Dark grey for secondary text/labels
    border_light = colors.HexColor('#DADCE0') # Light grey for subtle borders

    # Custom Paragraph Styles
    # Company Name (Large and bold)
    company_name_style = ParagraphStyle(
        name='CompanyName',
        fontSize=30, # Even larger for impact
        leading=36,
        textColor=primary_color,
        alignment=0,
        fontName='Helvetica-Bold' # Helvetica or Arial are clean, common choices
    )
    # Company Address/Contact Info
    company_info_style = ParagraphStyle(
        name='CompanyInfo',
        fontSize=9,
        leading=11,
        textColor=text_medium,
        alignment=0,
        fontName='Helvetica'
    )
    # Section Title (e.g., "Invoice Details", "Bill To")
    section_title_style = ParagraphStyle(
        name='SectionTitle',
        fontSize=12,
        leading=14,
        textColor=text_dark,
        alignment=0,
        fontName='Helvetica-Bold'
    )
    # Key Value Label (e.g., "Invoice #:", "Date:")
    label_style = ParagraphStyle(
        name='Label',
        fontSize=10,
        leading=12,
        textColor=text_medium,
        alignment=0,
        fontName='Helvetica'
    )
    # Key Value Data (e.g., "INV-001", "2023-10-26")
    data_style = ParagraphStyle(
        name='Data',
        fontSize=10,
        leading=12,
        textColor=text_dark,
        alignment=0,
        fontName='Helvetica-Bold'
    )
    # Item Table Header
    table_header_style = ParagraphStyle(
        name='TableHeader',
        fontSize=10,
        leading=12,
        textColor=text_dark,
        alignment=1, # Center alignment
        fontName='Helvetica-Bold'
    )
    # Item Table Cell
    table_cell_style = ParagraphStyle(
        name='TableCell',
        fontSize=9,
        leading=11,
        textColor=text_dark,
        alignment=1, # Center alignment
        fontName='Helvetica'
    )
    # Right-aligned Table Cell (for prices)
    table_cell_right_style = ParagraphStyle(
        name='TableCellRight',
        fontSize=9,
        leading=11,
        textColor=text_dark,
        alignment=2, # Right alignment
        fontName='Helvetica'
    )
    # Subtotal/Tax/Total Labels (right-aligned)
    summary_label_style = ParagraphStyle(
        name='SummaryLabel',
        fontSize=11,
        leading=13,
        textColor=text_dark,
        alignment=2, # Right alignment
        fontName='Helvetica'
    )
    # Grand Total Value (larger, bold, primary color)
    grand_total_value_style = ParagraphStyle(
        name='GrandTotalValue',
        fontSize=18,
        leading=22,
        textColor=primary_color,
        alignment=2, # Right alignment
        fontName='Helvetica-Bold'
    )
    # Footer Text
    footer_style = ParagraphStyle(
        name='Footer',
        fontSize=9,
        leading=11,
        textColor=text_medium,
        alignment=1, # Center alignment
        fontName='Helvetica'
    )

    # --- Header Section: Company Name & Info ---
    elements.append(Paragraph("<b>LAVANDERÍA MODERNA</b>", company_name_style))
    elements.append(Paragraph("Calle Ficticia 123, Lima, Perú | +51 987 654 321 | info@lavanderiamoderna.com", company_info_style))
    elements.append(Spacer(1, 0.5 * inch)) # More space after header

    # --- Invoice Details & Bill To (Side-by-Side Clean Layout) ---
    # Invoice Details
    invoice_details_data = [
        [Paragraph("<b>RECIBO #:</b>", label_style), Paragraph(f"{order.id}", data_style)],
        [Paragraph("<b>EMITIDO:</b>", label_style), Paragraph(datetime.now().strftime('%d/%m/%Y'), data_style)],
        [Paragraph("<b>VENCIMIENTO:</b>", label_style), Paragraph((datetime.now() + timedelta(days=7)).strftime('%d/%m/%Y'), data_style)],
    ]
    invoice_details_table = Table(invoice_details_data, colWidths=[1.5 * inch, 2.0 * inch])
    invoice_details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('GRID', (0,0), (-1,-1), 0.25, border_light), # Light borders for definition
        ('BACKGROUND', (0,0), (-1,-1), secondary_color),
    ]))

    # Bill To
    bill_to_data = [
        [Paragraph("<b>DESTINATARIO:</b>", section_title_style)],
        [Paragraph(f"{order.customer.name}", data_style)],
        [Paragraph(f"Código: {order.customer.customer_code}", label_style)],
    ]
    if order.customer.phone:
        bill_to_data.append([Paragraph(f"Teléfono: {order.customer.phone}", label_style)])
    if order.customer.email:
        bill_to_data.append([Paragraph(f"Correo: {order.customer.email}", label_style)])

    bill_to_table = Table(bill_to_data, colWidths=[3.0 * inch])
    bill_to_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))

    # Combine into a single table for two-column layout
    # Use nested tables for precise control
    combined_info = Table([[invoice_details_table, Spacer(1,1), bill_to_table]], colWidths=[3.5 * inch, 0.5 * inch, 3.0 * inch])
    combined_info.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(combined_info)
    elements.append(Spacer(1, 0.4 * inch))

    # --- Line Items Table ---
    elements.append(Paragraph("<b>DETALLES DEL SERVICIO</b>", section_title_style))
    elements.append(Spacer(1, 0.15 * inch))

    item_table_data = [
        [Paragraph('PRODUCTO/SERVICIO', table_header_style),
         Paragraph('DESCRIPCIÓN', table_header_style),
         Paragraph('CANT.', table_header_style),
         Paragraph('PRECIO UNIT. (S/)', table_header_style),
         Paragraph('TOTAL (S/)', table_header_style)]
    ]
    total = Decimal('0.00')
    for oc in order.ordercategory_set.all():
        item_total = oc.quantity * oc.category.price
        total += item_total
        item_table_data.append([
            Paragraph(oc.category.name, table_cell_style),
            Paragraph(oc.category.description or 'Lavado estándar', table_cell_style),
            Paragraph(str(oc.quantity), table_cell_style),
            Paragraph(f"{oc.category.price:.2f}", table_cell_right_style),
            Paragraph(f"{item_total:.2f}", table_cell_right_style)
        ])
    if order.weight and order.weight_price_per_kg:
        weight_total = order.weight * order.weight_price_per_kg
        total += weight_total
        item_table_data.append([
            Paragraph(f"Peso ({order.weight} kg)", table_cell_style),
            Paragraph('Lavado por peso', table_cell_style),
            Paragraph('1', table_cell_style),
            Paragraph(f"{order.weight_price_per_kg:.2f}", table_cell_right_style),
            Paragraph(f"{weight_total:.2f}", table_cell_right_style)
        ])

    item_table = Table(item_table_data, colWidths=[1.5 * inch, 2.0 * inch, 0.8 * inch, 1.2 * inch, 1.2 * inch])
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), secondary_color), # Light blue header background
        ('TEXTCOLOR', (0, 0), (-1, 0), text_dark),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),

        ('GRID', (0, 0), (-1, -1), 0.5, border_light), # All cells have light borders
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0,1), (-1,-1), 6),
        ('RIGHTPADDING', (0,1), (-1,-1), 6),
        ('TOPPADDING', (0,1), (-1,-1), 6),
        ('BOTTOMPADDING', (0,1), (-1,-1), 6),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 0.4 * inch))

    # --- Financial Summary (Right-aligned and prominent total) ---
    tax_rate = Decimal('0.13')
    tax = total * tax_rate
    grand_total = total + tax

    summary_data = [
        [Paragraph('Subtotal:', summary_label_style), Paragraph(f'S/{total:.2f}', data_style)],
        [Paragraph('Impuesto (13%):', summary_label_style), Paragraph(f'S/{tax:.2f}', data_style)],
        [Paragraph('TOTAL:', grand_total_value_style), Paragraph(f'S/{grand_total:.2f}', grand_total_value_style)]
    ]
    summary_table = Table(summary_data, colWidths=[5.0 * inch, 1.75 * inch]) # Wider first column for labels
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LINEABOVE', (0, -1), (-1, -1), 1, border_light), # Line above grand total
        ('LINEBELOW', (0, -1), (-1, -1), 2, primary_color), # Thicker line below grand total
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.5 * inch))

    # --- Footer Section: Message and QR Code ---
    footer_elements = []
    footer_elements.append(Paragraph("Gracias por tu preferencia. ¡Vuelve pronto!", footer_style))
    footer_elements.append(Spacer(1, 0.2 * inch))

    if order.qr_code and os.path.exists(order.qr_code.path):
        qr_image = Image(order.qr_code.path, 1.2 * inch, 1.2 * inch) # Slightly larger QR for readability
        qr_image.hAlign = 'CENTER'
        footer_elements.append(qr_image)

    footer_table = Table([[elem] for elem in footer_elements], colWidths=[letter[0] - 1.5*inch]) # Match document margins
    footer_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(footer_table)

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=recibo_pedido_{order.id}.pdf'
    response.write(buffer.getvalue())
    buffer.close()
    return response

@login_required
def payment_audit(request):
    orders = Order.objects.filter(payment_status__in=['PENDING', 'PARTIAL']).order_by('-created_at')
    paginator = Paginator(orders, 10)
    page_number = request.GET.get('page')
    page = paginator.get_page(page_number)
    return render(request, 'core/payment_audit.html', {'orders': page})

@login_required
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST' and order.status != 'CANCELLED':
        order.status = 'CANCELLED'
        order.save()
        messages.success(request, f'Pedido {order.id} anulado correctamente.')
    return redirect('manage_customer_orders', customer_code=order.customer.customer_code)

@login_required
def search_customers(request):
    query = request.GET.get('query', '')
    customers = Customer.objects.filter(
        Q(name__icontains=query) | Q(customer_code__icontains=query)
    )[:10]
    results = [
        {'id': customer.id, 'name': customer.name, 'code': customer.customer_code}
        for customer in customers
    ]
    return JsonResponse({'results': results})
@login_required
def manage_settings(request):
    # Definimos las claves de configuración y sus valores por defecto
    CONFIG_KEYS = {
        'business_name': 'Mi Lavandería',
        'business_address': 'Dirección no configurada',
        'business_phone': '',
        'default_price_per_kg': '5.00'
    }

    if request.method == 'POST':
        form = ConfigurationForm(request.POST)
        if form.is_valid():
            cleaned_data = form.cleaned_data
            
            # Itera y guarda cada ajuste usando update_or_create para seguridad
            AppConfiguration.objects.update_or_create(
                key='business_name', defaults={'value': cleaned_data['business_name']}
            )
            AppConfiguration.objects.update_or_create(
                key='business_address', defaults={'value': cleaned_data['business_address']}
            )
            AppConfiguration.objects.update_or_create(
                key='business_phone', defaults={'value': cleaned_data['business_phone']}
            )
            AppConfiguration.objects.update_or_create(
                key='default_price_per_kg', defaults={'value': str(cleaned_data['price_per_kg'])}
            )
            
            messages.success(request, 'La configuración ha sido actualizada correctamente.')
            return redirect('manage_settings')
    else:
        # Para GET, obtenemos los valores de la BD o usamos los por defecto
        db_configs = {c.key: c.value for c in AppConfiguration.objects.filter(key__in=CONFIG_KEYS.keys())}
        initial_data = {key: db_configs.get(key, default_val) for key, default_val in CONFIG_KEYS.items()}
        
        # Preparamos los datos para el formulario
        form = ConfigurationForm(initial={
            'business_name': initial_data.get('business_name'),
            'business_address': initial_data.get('business_address'),
            'business_phone': initial_data.get('business_phone'),
            'price_per_kg': Decimal(initial_data.get('default_price_per_kg'))
        })

    return render(request, 'core/settings.html', {'form': form})
@login_required
def mark_order_as_delivered(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        # Validación: No entregar si aún hay deuda
        if order.remaining_amount() > 0:
            messages.error(request, f'Error: El pedido #{order.id} no puede ser entregado porque tiene una deuda pendiente de S/ {order.remaining_amount()}.')
        else:
            order.status = 'DELIVERED'
            order.save()
            messages.success(request, f'Pedido #{order.id} marcado como ENTREGADO correctamente.')
        
        # Redirigir de vuelta a la página de donde vino
        return redirect('manage_customer_orders', customer_code=order.customer.customer_code)
    
    # Si no es POST, simplemente redirigir
    return redirect('dashboard')

# === INICIO DE CÓDIGO AÑADIDO ===

@login_required
def product_list(request):
    """Muestra una lista de todos los productos."""
    products = Product.objects.all().order_by('name')
    return render(request, 'core/product_list.html', {'products': products})


@login_required
def add_product(request):
    """Maneja la creación de un nuevo producto."""
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Producto agregado exitosamente.')
            return redirect('product_list')
    else:
        form = ProductForm()
    return render(request, 'core/product_form.html', {'form': form, 'title': 'Agregar Nuevo Producto'})


@login_required
def edit_product(request, product_id):
    """Maneja la edición de un producto existente."""
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Producto actualizado exitosamente.')
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'core/product_form.html', {'form': form, 'title': f'Editando: {product.name}'})


@login_required
def delete_product(request, product_id):
    """Elimina un producto."""
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        try:
            product.delete()
            messages.success(request, f'Producto "{product.name}" eliminado.')
        except ProtectedError: # <- ESTA ES LA LÍNEA CORREGIDA
            messages.error(request, f'No se puede eliminar "{product.name}" porque está asociado a ventas existentes.')
    return redirect('product_list')


@login_required
def create_sale(request):
    """
    Crea una nueva venta desde la interfaz dinámica del POS.
    Maneja GET para cargar la página y POST con JSON para crear la venta.
    """
    if request.method == 'POST':
        try:
            # Leemos los datos JSON enviados por JavaScript
            data = json.loads(request.body)
            cart_items = data.get('cart', [])
            customer_id = data.get('customer_id')
            payment_method = data.get('payment_method')
            payment_status = data.get('payment_status')

            if not cart_items:
                return JsonResponse({'success': False, 'error': 'El carrito está vacío.'}, status=400)

            with transaction.atomic():
                # 1. Crear el objeto de la Venta
                customer = None
                if customer_id:
                    customer = Customer.objects.get(id=customer_id)
                
                sale = Sale.objects.create(
                    customer=customer,
                    payment_method=payment_method,
                    payment_status=payment_status,
                    total_amount=0 # Se calculará después
                )

                # 2. Recorrer los artículos del carrito y crear los SaleItem
                for item_data in cart_items:
                    product = Product.objects.get(id=item_data['id'])

                    # Doble verificación de stock para evitar problemas de concurrencia
                    if product.stock < item_data['quantity']:
                        # Si no hay stock, la transacción se revierte automáticamente
                        raise ValueError(f"Stock insuficiente para el producto: {product.name}")

                    SaleItem.objects.create(
                        sale=sale,
                        product=product,
                        quantity=item_data['quantity'],
                        unit_price=product.price
                    )
                    
                    # Actualizar el stock de forma segura
                    product.stock = F('stock') - item_data['quantity']
                    product.save()

                # 3. Calcular el total final y guardar
                sale.calculate_total()
            
            # 4. Devolver una respuesta exitosa con la URL del ticket
            ticket_url = reverse('print_sale_ticket', args=[sale.id])
            return JsonResponse({'success': True, 'ticket_url': ticket_url})

        except Customer.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'El cliente seleccionado no existe.'}, status=400)
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Uno de los productos no existe.'}, status=400)
        except ValueError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        except Exception as e:
            # Para cualquier otro error inesperado
            return JsonResponse({'success': False, 'error': f'Error inesperado: {str(e)}'}, status=500)

    # La lógica para la petición GET se mantiene, carga la página inicial
    else:
        sale_form = SaleForm()
        all_products = Product.objects.filter(stock__gt=0).order_by('name')

    context = {
        'sale_form': sale_form,
        'all_products': all_products,
    }
    return render(request, 'core/create_sale.html', context)


@login_required
def sales_history(request):
    """Muestra el historial de todas las ventas."""
    sales = Sale.objects.all().order_by('-created_at')
    paginator = Paginator(sales, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'core/sales_history.html', {'page_obj': page_obj})


@login_required
def sale_receipt_pdf(request, sale_id):
    """Genera un recibo en PDF para una venta específica."""
    sale = get_object_or_404(Sale, id=sale_id)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesizes=letter)
    styles = getSampleStyleSheet()
    elements = []

    # Título
    elements.append(Paragraph(f"Recibo de Venta #{sale.id}", styles['h1']))
    elements.append(Spacer(1, 0.2 * inch))

    # Información del cliente
    customer_info = f"Cliente: {sale.customer.name if sale.customer else 'Venta de Mostrador'}"
    elements.append(Paragraph(customer_info, styles['BodyText']))
    elements.append(Paragraph(f"Fecha: {sale.created_at.strftime('%d/%m/%Y %H:%M')}", styles['BodyText']))
    elements.append(Spacer(1, 0.2 * inch))

    # Tabla de productos
    table_data = [['Producto', 'Cant.', 'P. Unitario', 'Subtotal']]
    for item in sale.saleitem_set.all():
        subtotal = item.quantity * item.unit_price
        table_data.append([
            item.product.name,
            str(item.quantity),
            f"S/ {item.unit_price:.2f}",
            f"S/ {subtotal:.2f}"
        ])
    
    table_data.append(['', '', Paragraph('<b>Total:</b>', styles['BodyText']), Paragraph(f"<b>S/ {sale.total_amount:.2f}</b>", styles['BodyText'])])
    
    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (2, -1), (-1, -1), 'RIGHT'), # Alinear el total a la derecha
    ]))
    
    elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=recibo_venta_{sale.id}.pdf'
    response.write(buffer.getvalue())
    buffer.close()
    return response

# ==============================================================================
# SECCIÓN DE IMPRESIÓN DE TICKET (NUEVA Y MEJORADA)
# ==============================================================================

@login_required
@login_required
def print_order_ticket(request, order_id):
    """
    Prepara los datos para el ticket de un pedido específico.
    Esta vista genera el enlace seguro para el QR y para WhatsApp usando el 'short_id'.
    """
    try:
        # Buscamos el pedido por su ID normal, que viene de la URL interna de la app.
        order = Order.objects.get(id=order_id)
        
        # Obtenemos la configuración de la app (nombre del negocio, etc.)
        app_config_qs = AppConfiguration.objects.all()
        app_config = {c.key: c.value for c in app_config_qs}

        # --- ¡AQUÍ ESTÁ LA MAGIA! ---
        # 1. Creamos la URL segura usando el 'short_id' del pedido.
        #    reverse('order_status', ...) busca la URL con name='order_status'
        #    y le pasa el short_id como argumento.
        qr_url = request.build_absolute_uri(reverse('order_status', args=[order.short_id]))

        # 2. Preparamos el enlace de WhatsApp (si el cliente tiene teléfono)
        whatsapp_link = ""
        if order.customer.phone:
            phone_number = order.customer.phone.strip().replace(" ", "")
            if not phone_number.startswith('51'):
                phone_number = f"51{phone_number}"

            business_name = app_config.get('business_name', 'tu lavandería')
            
            # El mensaje ahora incluye la nueva URL corta y segura.
            message_text = (
                f"Hola {order.customer.name}, aquí tienes el resumen de tu pedido #{order.order_code} en *{business_name}*.\n\n"
                f"Total: *S/ {order.total_price:.2f}*\n\n"
                f"Puedes ver el estado de tu pedido en cualquier momento aquí:\n{qr_url}"
            )
            encoded_message = quote(message_text)
            whatsapp_link = f"https://wa.me/{phone_number}?text={encoded_message}"

        # 3. Pasamos todos los datos a la plantilla del ticket.
        context = {
            'order': order,
            'app_config': app_config,
            'qr_url': qr_url,
            'whatsapp_link': whatsapp_link,
        }
        return render(request, 'core/order_ticket.html', context)
        
    except Order.DoesNotExist:
        messages.error(request, "El pedido que intentas procesar no existe.")
        return redirect('dashboard')

# === FIN DE CÓDIGO AÑADIDO ===

# ==============================================================================
# SECCIÓN DE REPORTES (CORREGIDA Y OPTIMIZADA)
# ==============================================================================

@login_required
@login_required
def reports_dashboard(request):
    """ Muestra el menú principal de la sección de reportes. """
    return render(request, 'core/reports_dashboard.html')

@login_required
def orders_report(request):
    """
    Muestra un reporte de pedidos, con filtros por cliente, fecha y estado.
    """
    report_filter_form = ReportFilterForm(request.GET)
    orders = Order.objects.select_related('customer').all().order_by('-created_at')

    if report_filter_form.is_valid():
        date_from = report_filter_form.cleaned_data.get('date_from')
        date_to = report_filter_form.cleaned_data.get('date_to')
        status = report_filter_form.cleaned_data.get('status')
        customer = report_filter_form.cleaned_data.get('customer')

        if date_from: orders = orders.filter(created_at__date__gte=date_from)
        if date_to: orders = orders.filter(created_at__date__lte=date_to)
        if status: orders = orders.filter(status=status)
        if customer: orders = orders.filter(customer=customer)

    # --- CORRECCIÓN AQUÍ ---
    # Al calcular el total, excluimos los pedidos anulados del queryset filtrado.
    total_amount = orders.exclude(status='CANCELLED').aggregate(
        total=Coalesce(Sum(F('original_calculated_price') - F('discount_amount')), Decimal('0.0'))
    )['total']
    
    total_orders = orders.count()

    context = {
        'report_filter_form': report_filter_form,
        'orders': orders,
        'total_orders': total_orders,
        'total_amount': total_amount,
        'report_type': 'orders', 
    }
    return render(request, 'core/reports/orders_report.html', context)


@login_required
def income_report(request):
    """
    Muestra un reporte de ingresos, con filtros por cliente y fecha.
    """
    report_filter_form = ReportFilterForm(request.GET)
    
    # --- CORRECCIÓN AQUÍ ---
    # Excluimos los pedidos anulados desde el inicio de la consulta, ya que
    # un pedido anulado nunca debe contar como un ingreso.
    orders = Order.objects.select_related('customer').filter(
        payment_status__in=['PAID', 'PARTIAL']
    ).exclude(status='CANCELLED').order_by('-created_at')

    if report_filter_form.is_valid():
        date_from = report_filter_form.cleaned_data.get('date_from')
        date_to = report_filter_form.cleaned_data.get('date_to')
        customer = report_filter_form.cleaned_data.get('customer')

        if date_from: orders = orders.filter(created_at__date__gte=date_from)
        if date_to: orders = orders.filter(created_at__date__lte=date_to)
        if customer: orders = orders.filter(customer=customer)
            
    total_income = orders.aggregate(
        total=Coalesce(Sum(F('original_calculated_price') - F('discount_amount')), Decimal('0.0'))
    )['total']

    context = {
        'report_filter_form': report_filter_form,
        'orders': orders,
        'total_income': total_income,
        'report_type': 'income',
    }
    return render(request, 'core/reports/income_report.html', context)


@login_required
def sales_report(request):
    """
    Muestra un reporte de ventas de productos (no de lavandería).
    """
    report_filter_form = ReportFilterForm(request.GET)
    sales = Sale.objects.all().order_by('-created_at')

    if report_filter_form.is_valid():
        date_from = report_filter_form.cleaned_data.get('date_from')
        date_to = report_filter_form.cleaned_data.get('date_to')
        if date_from: sales = sales.filter(created_at__date__gte=date_from)
        if date_to: sales = sales.filter(created_at__date__lte=date_to)

    total_sales_amount = sales.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0.0')))['total']

    context = {
        'report_filter_form': report_filter_form,
        'sales': sales,
        'total_sales_amount': total_sales_amount,
        'hide_customer_filter': True,
        'hide_status_filter': True,
        'report_type': 'sales',
    }
    # --- RUTA CORREGIDA ---
    return render(request, 'core/reports/sales_report.html', context)

@login_required
def customers_report(request):
    form = ReportFilterForm(request.GET or None)
    customers = Customer.objects.annotate(
        total_orders=Count('order'),
        total_sales=Count('sale'),
        # --- CORRECCIÓN APLICADA AQUÍ ---
        weight_price=Sum(
            ExpressionWrapper(
                F('order__weight') * F('order__weight_price_per_kg'),
                output_field=DecimalField()
            ),
            filter=~Q(order__status='CANCELLED') # Excluir anulados
        ),
        # --- CORRECCIÓN APLICADA AQUÍ ---
        category_price=Sum(
            F('order__ordercategory__quantity') * F('order__ordercategory__category__price'),
            output_field=DecimalField(),
            filter=~Q(order__status='CANCELLED') # Excluir anulados
        ),
        sales_total=Sum('sale__total_amount')
    ).annotate(
        total_spent=ExpressionWrapper(
            Coalesce(F('weight_price'), 0) + Coalesce(F('category_price'), 0) + Coalesce(F('sales_total'), 0),
            output_field=DecimalField()
        )
    )
    
    if form.is_valid():
        date_from = form.cleaned_data.get('date_from')
        date_to = form.cleaned_data.get('date_to')
        
        if date_from:
            customers = customers.filter(
                Q(order__created_at__date__gte=date_from) | Q(sale__created_at__date__gte=date_from)
            ).distinct()
        if date_to:
            customers = customers.filter(
                Q(order__created_at__date__lte=date_to) | Q(sale__created_at__date__lte=date_to)
            ).distinct()
    
    paginator = Paginator(customers, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'form': form,
        'customers': page_obj,
        'report_type': 'customers'
    }
    return render(request, 'core/customers_report.html', context)

@login_required
def export_report_pdf(request, report_type):
    form = ReportFilterForm(request.GET or None)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    if form.is_valid():
        date_from = form.cleaned_data.get('date_from')
        date_to = form.cleaned_data.get('date_to')
        customer = form.cleaned_data.get('customer')
        payment_method = form.cleaned_data.get('payment_method')
        order_status = form.cleaned_data.get('order_status')
        
        if report_type == 'income':
            # --- CORRECCIÓN AQUÍ ---
            orders = Order.objects.filter(payment_status__in=['PAID', 'PARTIAL']).exclude(status='CANCELLED')
            sales = Sale.objects.all()
            if date_from:
                orders = orders.filter(created_at__date__gte=date_from)
                sales = sales.filter(created_at__date__gte=date_from)
            if date_to:
                orders = orders.filter(created_at__date__lte=date_to)
                sales = sales.filter(created_at__date__lte=date_to)
            if customer:
                orders = orders.filter(customer=customer)
                sales = sales.filter(customer=customer)
            if payment_method:
                orders = orders.filter(payment_method=payment_method)
                
            elements.append(Paragraph("Reporte de Ingresos", styles['h1']))
            elements.append(Spacer(1, 0.2 * inch))
            table_data = [['Fecha', 'Tipo', 'Cliente', 'Monto (S/)']]
            for order in orders:
                table_data.append([
                    order.created_at.strftime('%d/%m/%Y'),
                    'Pedido',
                    order.customer.name,
                    f"{order.total_price:.2f}"
                ])
            for sale in sales:
                table_data.append([
                    sale.created_at.strftime('%d/%m/%Y'),
                    'Venta',
                    sale.customer.name if sale.customer else 'Mostrador',
                    f"{sale.total_amount:.2f}"
                ])
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
        
        elif report_type == 'orders':
            # --- CORRECCIÓN AQUÍ --- (Aunque esta parte no calcula un total, es buena práctica mantener la consistencia)
            orders = Order.objects.select_related('customer').all()
            if date_from:
                orders = orders.filter(created_at__date__gte=date_from)
            if date_to:
                orders = orders.filter(created_at__date__lte=date_to)
            if customer:
                orders = orders.filter(customer=customer)
            if order_status:
                orders = orders.filter(status=order_status)
            if payment_method:
                orders = orders.filter(payment_method=payment_method)
                
            elements.append(Paragraph("Reporte de Pedidos", styles['h1']))
            elements.append(Spacer(1, 0.2 * inch))
            table_data = [['ID', 'Fecha', 'Cliente', 'Estado', 'Monto (S/)']]
            for order in orders:
                # El monto de los pedidos anulados se mostrará, pero no se sumará si hubiera un total.
                monto_display = "0.00" if order.status == 'CANCELLED' else f"{order.total_price:.2f}"
                table_data.append([
                    str(order.id),
                    order.created_at.strftime('%d/%m/%Y'),
                    order.customer.name,
                    order.get_status_display(),
                    monto_display
                ])
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
        
        # El resto de los tipos de reporte ('sales', 'customers') no necesitan cambios en esta parte
        elif report_type == 'sales':
            sales = Sale.objects.select_related('customer').all()
            if date_from:
                sales = sales.filter(created_at__date__gte=date_from)
            if date_to:
                sales = sales.filter(created_at__date__lte=date_to)
            if customer:
                sales = sales.filter(customer=customer)
                
            elements.append(Paragraph("Reporte de Ventas", styles['h1']))
            elements.append(Spacer(1, 0.2 * inch))
            table_data = [['ID', 'Fecha', 'Cliente', 'Monto (S/)']]
            for sale in sales:
                table_data.append([
                    str(sale.id),
                    sale.created_at.strftime('%d/%m/%Y'),
                    sale.customer.name if sale.customer else 'Mostrador',
                    f"{sale.total_amount:.2f}"
                ])
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
        
        elif report_type == 'customers':
            customers = Customer.objects.annotate(
                total_orders=Count('order'),
                total_sales=Count('sale'),
                weight_price=Sum(
                    ExpressionWrapper(
                        F('order__weight') * F('order__weight_price_per_kg'),
                        output_field=DecimalField()
                    ),
                    filter=~Q(order__status='CANCELLED')
                ),
                category_price=Sum(
                    F('order__ordercategory__quantity') * F('order__ordercategory__category__price'),
                    output_field=DecimalField(),
                    filter=~Q(order__status='CANCELLED')
                ),
                sales_total=Sum('sale__total_amount')
            ).annotate(
                total_spent=ExpressionWrapper(
                    Coalesce(F('weight_price'), 0) + Coalesce(F('category_price'), 0) + Coalesce(F('sales_total'), 0),
                    output_field=DecimalField()
                )
            )
            if date_from:
                customers = customers.filter(
                    Q(order__created_at__date__gte=date_from) | Q(sale__created_at__date__gte=date_from)
                ).distinct()
            if date_to:
                customers = customers.filter(
                    Q(order__created_at__date__lte=date_to) | Q(sale__created_at__date__lte=date_to)
                ).distinct()
                
            elements.append(Paragraph("Reporte de Clientes", styles['h1']))
            elements.append(Spacer(1, 0.2 * inch))
            table_data = [['Nombre', 'Código', 'Total Pedidos', 'Total Ventas', 'Gasto Total (S/)']]
            for customer in customers:
                table_data.append([
                    customer.name,
                    customer.customer_code,
                    str(customer.total_orders),
                    str(customer.total_sales),
                    f"{customer.total_spent:.2f}" if customer.total_spent else "0.00"
                ])
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename={report_type}_report.pdf'
    response.write(buffer.getvalue())
    buffer.close()
    return response

@login_required
def export_report_csv(request, report_type):
    form = ReportFilterForm(request.GET or None)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={report_type}_report.csv'
    writer = csv.writer(response)
    
    if form.is_valid():
        if report_type == 'income':
            # --- CORRECCIÓN AQUÍ ---
            orders = Order.objects.filter(payment_status__in=['PAID', 'PARTIAL']).exclude(status='CANCELLED')
            sales = Sale.objects.all()
            date_from = form.cleaned_data.get('date_from')
            date_to = form.cleaned_data.get('date_to')
            customer = form.cleaned_data.get('customer')
            payment_method = form.cleaned_data.get('payment_method')
            
            if date_from:
                orders = orders.filter(created_at__date__gte=date_from)
                sales = sales.filter(created_at__date__gte=date_from)
            if date_to:
                orders = orders.filter(created_at__date__lte=date_to)
                sales = sales.filter(created_at__date__lte=date_to)
            if customer:
                orders = orders.filter(customer=customer)
                sales = sales.filter(customer=customer)
            if payment_method:
                orders = orders.filter(payment_method=payment_method)
                
            writer.writerow(['Fecha', 'Tipo', 'Cliente', 'Monto'])
            for order in orders:
                writer.writerow([
                    order.created_at.strftime('%d/%m/%Y'),
                    'Pedido',
                    order.customer.name,
                    order.total_price
                ])
            for sale in sales:
                writer.writerow([
                    sale.created_at.strftime('%d/%m/%Y'),
                    'Venta',
                    sale.customer.name if sale.customer else 'Mostrador',
                    sale.total_amount
                ])
    
    return response

def customer_list(request):
    today = date.today()
    customer_filter_form = CustomerFilterForm(request.GET)
    customer_list_qs = Customer.objects.all()

    if customer_filter_form.is_valid():
        search_query = customer_filter_form.cleaned_data.get('search_query')
        order_status = customer_filter_form.cleaned_data.get('order_status')
        payment_status = customer_filter_form.cleaned_data.get('payment_status')
        if search_query:
            customer_list_qs = customer_list_qs.filter(
                Q(name__icontains=search_query) | Q(customer_code__icontains=search_query) | Q(phone__icontains=search_query)
            )
        if order_status: customer_list_qs = customer_list_qs.filter(order__status=order_status).distinct()
        if payment_status: customer_list_qs = customer_list_qs.filter(order__payment_status=payment_status).distinct()

    ninety_days_ago = today - timedelta(days=90)
    seven_days_ago = today - timedelta(days=7)
    
    # --- CORRECCIÓN APLICADA AQUÍ ---
    top_customer_ids = list(Customer.objects.annotate(
        total_spent=Coalesce(Sum(
            (F('order__original_calculated_price') - F('order__discount_amount')),
            filter=~Q(order__status='CANCELLED') # Excluir anulados
        ), Decimal('0.0'))
    ).order_by('-total_spent').values_list('id', flat=True)[:5])

    # --- CORRECCIÓN APLICADA AQUÍ ---
    customer_list_annotated = customer_list_qs.annotate(
        latest_order_date=Max('order__created_at'),
        total_spent=Coalesce(Sum(
            (F('order__original_calculated_price') - F('order__discount_amount')),
            filter=~Q(order__status='CANCELLED') # Excluir anulados
        ), Decimal('0.0')),
        is_new=Case(When(created_at__gte=seven_days_ago, then=Value(True)), default=Value(False), output_field=BooleanField()),
        is_inactive=Case(
            When(latest_order_date__isnull=True, then=Value(False)),
            When(latest_order_date__lt=ninety_days_ago, then=Value(True)),
            default=Value(False),
            output_field=BooleanField()
        ),
        is_top=Case(When(id__in=top_customer_ids, then=Value(True)), default=Value(False), output_field=BooleanField())
    ).order_by('-is_top', '-total_spent', 'name')

    thirty_days_ago = today - timedelta(days=30)
    new_customers_this_month = Customer.objects.filter(created_at__year=today.year, created_at__month=today.month).count()
    active_customers = Customer.objects.filter(order__created_at__gte=thirty_days_ago).distinct().count()
    inactive_customers_count = customer_list_annotated.filter(is_inactive=True).count()
    
    paginator = Paginator(customer_list_annotated, 15)
    page_number = request.GET.get('page')
    try:
        customers_page = paginator.page(page_number)
    except PageNotAnInteger:
        customers_page = paginator.page(1)
    except EmptyPage:
        customers_page = paginator.page(paginator.num_pages)

    context = {
        'customers': customers_page, 'customer_filter_form': customer_filter_form,
        'new_customers_this_month': new_customers_this_month, 'active_customers': active_customers,
        'inactive_customers_count': inactive_customers_count,
    }
    return render(request, 'core/customer_list.html', context)

@login_required
def export_customers_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="clientes_{date.today()}.csv"'
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response)
    writer.writerow(['Codigo Cliente', 'Nombre', 'Telefono', 'Email', 'Fecha de Registro'])
    customers = Customer.objects.all().values_list('customer_code', 'name', 'phone', 'email', 'created_at')
    for customer in customers:
        row = list(customer)
        if isinstance(row[4], date): row[4] = row[4].strftime("%Y-%m-%d %H:%M")
        writer.writerow(row)
    return response


@login_required
def print_sale_ticket(request, sale_id):
    """
    Prepara los datos y muestra un ticket imprimible para una venta específica.
    """
    try:
        sale = get_object_or_404(Sale.objects.select_related('customer'), id=sale_id)
        app_config_qs = AppConfiguration.objects.all()
        app_config = {c.key: c.value for c in app_config_qs}

        whatsapp_link = ""
        # Solo genera enlace de WhatsApp si la venta está asociada a un cliente con teléfono
        if sale.customer and sale.customer.phone:
            phone_number = sale.customer.phone.strip().replace(" ", "")
            if not phone_number.startswith('51'):
                phone_number = f"51{phone_number}"

            business_name = app_config.get('business_name', 'tu tienda')
            
            message_text = (
                f"Hola {sale.customer.name}, gracias por tu compra en *{business_name}*.\n\n"
                f"Total de la Venta #{sale.id}: *S/ {sale.total_amount:.2f}*"
            )
            encoded_message = quote(message_text)
            whatsapp_link = f"https://wa.me/{phone_number}?text={encoded_message}"
        
        context = {
            'sale': sale,
            'app_config': app_config,
            'whatsapp_link': whatsapp_link,
        }
        # Renderiza la nueva plantilla de ticket
        return render(request, 'core/sale_ticket.html', context)
        
    except Sale.DoesNotExist:
        messages.error(request, "La venta que intentas ver no existe.")
        return redirect('sales_history')