# laundry_app/core/admin.py

from django.contrib import admin
from django import forms  # <-- IMPORTANTE: Añadimos la importación de forms
from .models import (
    Customer, 
    Category, 
    Order, 
    OrderCategory, 
    AppConfiguration, 
    Product, 
    Sale, 
    SaleItem
)

# --- INICIO DE LA PERSONALIZACIÓN DE TÍTULOS ---

# Este es el título principal en la cabecera de cada página del admin
admin.site.site_header = "Panel de Lavandería Nicold"

# Este es el título que aparece en la pestaña del navegador
admin.site.site_title = "Portal de Administración"

# Este es el título que aparece en la página de inicio del admin
admin.site.index_title = "Bienvenido al Panel de Gestión"

# --- FIN DE LA PERSONALIZACIÓN ---
# --- Formularios Personalizados para el Admin (Aquí definimos las traducciones) ---

class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = '__all__'
        labels = {
            'customer': 'Cliente',
            'status': 'Estado del Pedido',
            'payment_status': 'Estado del Pago',
            'payment_method': 'Método de Pago',
            'weight': 'Peso (Kg)',
            'notes': 'Notas Adicionales',
            'partial_amount': 'Monto Adelantado',
            'discount_amount': 'Monto de Descuento',
            'payment_proof': 'Comprobante de Pago',
        }

class CustomerAdminForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = '__all__'
        labels = {
            'name': 'Nombre Completo',
            'phone': 'Teléfono de Contacto',
            'email': 'Correo Electrónico',
        }

# --- Clases del Admin que usarán los formularios personalizados ---

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm  # <-- AQUÍ le decimos al admin que use nuestro formulario personalizado
    
    list_display = ('id', 'customer', 'status', 'payment_status', 'created_at')
    list_filter = ('status', 'payment_status', 'created_at')
    search_fields = ('id', 'customer__name')
    readonly_fields = ('short_id', 'order_code', 'qr_code', 'created_at', 'updated_at', 'total_price', 'original_calculated_price')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    form = CustomerAdminForm # <-- Aplicamos el formulario personalizado para Cliente
    
    list_display = ('name', 'customer_code', 'phone', 'created_at')
    search_fields = ('name', 'customer_code', 'phone')
    readonly_fields = ('customer_code', 'qr_code', 'created_at')


# --- Registros simples para los demás modelos ---
# Estos no necesitan un formulario de edición tan complejo, por lo que un registro
# simple es suficiente. Si quisieras traducir sus campos, seguirías el mismo patrón:
# crear un ModelForm y asignarlo.

admin.site.register(Category)
admin.site.register(AppConfiguration)
admin.site.register(Product)
admin.site.register(Sale)