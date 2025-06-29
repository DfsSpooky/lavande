from django import forms
from .models import Customer, Order, Category, OrderCategory, AppConfiguration, Product, Sale, SaleItem
from django_select2.forms import Select2Widget
from decimal import Decimal

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email']
        labels = {
            'name': 'Nombre',
            'phone': 'Teléfono',
            'email': 'Correo Electrónico',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'phone': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'email': forms.EmailInput(attrs={'class': 'w-full p-2 border rounded'}),
        }

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        # Definimos los campos que queremos en el formulario principal
        fields = ['customer', 'weight', 'weight_price_per_kg', 'notes']
        # Asignamos las etiquetas en español
        labels = {
            'customer': 'Cliente',
            'weight': 'Peso (Kg)',
            'weight_price_per_kg': 'Precio por Kilo (S/)',
            'notes': 'Notas Adicionales',
        }
        widgets = {
            'customer': forms.Select(attrs={'class': 'select2-field'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ej: Ropa delicada, no usar secadora...'}),
            'weight': forms.NumberInput(attrs={'placeholder': 'Ej: 5.5'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacemos que el campo de precio por kilo no sea editable por el usuario
        self.fields['weight_price_per_kg'].widget.attrs['readonly'] = True
        self.fields['weight_price_per_kg'].widget.attrs['class'] = 'bg-gray-100'

        # --- CORRECCIÓN ---
        # Obtenemos el precio por kilo desde la configuración de forma segura
        try:
            # Buscamos la configuración específica por su clave
            price_setting = AppConfiguration.objects.get(key='default_price_per_kg')
            # Establecemos el valor inicial del campo, convirtiéndolo a Decimal
            self.fields['weight_price_per_kg'].initial = Decimal(price_setting.value)
        except (AppConfiguration.DoesNotExist, ValueError):
            # Si no se encuentra o el valor no es un número, usamos un valor por defecto
            # Esto evita que la aplicación se caiga si la configuración no está establecida
            self.fields['weight_price_per_kg'].initial = Decimal('5.00')

class OrderEditForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            'weight', 'notes', 'status', 'payment_status', 
            'payment_method', 'partial_amount', 'discount_amount'
        ]
        labels = {
            'weight': 'Peso (Kg)',
            'notes': 'Notas Adicionales',
            'status': 'Estado del Pedido',
            'payment_status': 'Estado del Pago',
            'payment_method': 'Método de Pago',
            'partial_amount': 'Monto Adelantado (S/)',
            'discount_amount': 'Descuento (S/)'
        }
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
            'status': forms.Select(),
            'payment_status': forms.Select(attrs={'id': 'payment_status_select'}),
            'payment_method': forms.Select(),
            'partial_amount': forms.NumberInput(attrs={'id': 'partial_amount_input'}),
            'discount_amount': forms.NumberInput(),
        }

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'price', 'description']
        labels = {
            'name': 'Nombre',
            'price': 'Precio',
            'description': 'Descripción',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'price': forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'w-full p-2 border rounded', 'rows': 4}),
        }

class OrderCategoryForm(forms.ModelForm):
    quantity = forms.IntegerField(min_value=1, label='Cantidad', widget=forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'min': '1'}))

    class Meta:
        model = OrderCategory
        fields = ['category', 'quantity']
        labels = {
            'category': 'Categoría',
        }
        widgets = {
            'category': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
        }

class OrderCategoryInlineForm(forms.ModelForm):
    class Meta:
        model = Order.categories.through
        fields = ['category', 'quantity']
        widgets = {
            'quantity': forms.NumberInput(attrs={'min': '1', 'value': '1'}),
        }
        labels = {
            'category': 'Categoría',
            'quantity': 'Cantidad'
        }

class CustomerFilterForm(forms.Form):
    """
    Formulario completo para la lista de clientes, con todos los filtros.
    """
    search_query = forms.CharField(
        label="Buscar Cliente",
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Buscar por nombre, código o teléfono...'})
    )
    order_status = forms.ChoiceField(
        choices=[('', 'Cualquier Estado de Pedido')] + Order.STATUS_CHOICES,
        required=False,
        label="Estado del Pedido"
    )
    payment_status = forms.ChoiceField(
        choices=[('', 'Cualquier Estado de Pago')] + Order.PAYMENT_STATUS_CHOICES,
        required=False,
        label="Estado de Pago"
    )

    # --- INICIO DE NUEVOS CAMPOS DE FILTRO ---
    # Filtro por estado del pedido del cliente
    order_status = forms.ChoiceField(
        choices=[('', 'Cualquier Estado de Pedido')] + Order.STATUS_CHOICES,
        required=False,
        label="Estado del Pedido"
    )

    # Filtro por estado de pago del pedido del cliente
    payment_status = forms.ChoiceField(
        choices=[('', 'Cualquier Estado de Pago')] + Order.PAYMENT_STATUS_CHOICES,
        required=False,
        label="Estado de Pago"
    )

class OrderFilterForm(forms.Form):
    status = forms.ChoiceField(
        choices=[('', 'Todos')] + Order.STATUS_CHOICES,
        required=False,
        label='Estado del Pedido',
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'})
    )
    payment_status = forms.ChoiceField(
        choices=[('', 'Todos')] + Order.PAYMENT_STATUS_CHOICES,
        required=False,
        label='Estado de Pago',
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'})
    )
    date_from = forms.DateField(
        required=False,
        label='Desde',
        widget=forms.DateInput(attrs={'class': 'w-full p-2 border rounded', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        label='Hasta',
        widget=forms.DateInput(attrs={'class': 'w-full p-2 border rounded', 'type': 'date'})
    )

class ReceiveOrderForm(forms.Form):
    customer_code = forms.CharField(
        label='Código de Cliente',
        required=True,
        widget=forms.TextInput(attrs={'class': 'w-full p-2 border rounded', 'placeholder': 'Ej: 1234', 'id': 'id_customer_code'})
    )
    weight = forms.DecimalField(
        required=False,
        label='Peso (kg)',
        widget=forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'step': '0.01'})
    )
    notes = forms.CharField(
        required=False,
        label='Notas',
        widget=forms.Textarea(attrs={'class': 'w-full p-2 border rounded', 'rows': 4})
    )
class ConfigurationForm(forms.Form):
    business_name = forms.CharField(
        label='Nombre del Negocio', 
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Mi Lavandería Moderna'})
    )
    business_address = forms.CharField(
        label='Dirección del Negocio', 
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Jr. Ficticio 123, Ciudad'})
    )
    business_phone = forms.CharField(
        label='Teléfono de Contacto', 
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Ej: 987654321'})
    )
    price_per_kg = forms.DecimalField(
        label='Precio Estándar por Kilo (S/)',
        min_value=Decimal('0.00'),
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01'})
    )


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['customer', 'payment_method', 'payment_status']
        labels = {
            'customer': 'Cliente (Opcional)',
            'payment_method': 'Método de Pago',
            'payment_status': 'Estado del Pago',
        }
        widgets = {
            'customer': Select2Widget(attrs={'class': 'w-full', 'data-placeholder': 'Seleccione un cliente o déjelo en blanco para una venta de mostrador'}),
            'payment_method': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'payment_status': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'price', 'stock', 'image']
        labels = {
            'name': 'Nombre del Producto',
            'description': 'Descripción',
            'price': 'Precio (S/)',
            'stock': 'Cantidad en Stock',
            'image': 'Imagen del Producto'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'description': forms.Textarea(attrs={'class': 'w-full p-2 border rounded', 'rows': 3}),
            'price': forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'step': '0.01'}),
            'stock': forms.NumberInput(attrs={'class': 'w-full p-2 border rounded'}),
            'image': forms.FileInput(attrs={'class': 'w-full p-2 border rounded'}),
        }


class SaleItemForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(stock__gt=0),
        label='Producto',
        widget=Select2Widget(attrs={'class': 'w-full', 'data-placeholder': 'Seleccione un producto'}),
        required=False  # <-- Cambio clave: permite que el campo esté vacío
    )
    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        label='Cantidad',
        widget=forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'min': '1'}),
        required=False  # <-- Cambio clave: permite que el campo esté vacío
    )

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')

        # Si el usuario llenó un campo pero no el otro, damos un error.
        if product and not quantity:
            self.add_error('quantity', 'Debes especificar una cantidad.')
        
        if quantity and not product:
            self.add_error('product', 'Debes seleccionar un producto.')

        # Si ambos campos están llenos, validamos el stock.
        if product and quantity:
            if quantity > product.stock:
                self.add_error('quantity', f'No hay stock suficiente. Disponible: {product.stock}')
        
        return cleaned_data
# === FIN DE CÓDIGO AÑADIDO ===

class ReportFilterForm(forms.Form):
    """
    Formulario unificado para todos los reportes, ahora incluye filtro por cliente.
    """
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all().order_by('name'),
        required=False,
        label="Cliente",
        # Usaremos JS en la plantilla para convertir esto en un buscador Select2
        widget=forms.Select(attrs={'id': 'customer-select2'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Desde"
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Hasta"
    )
    status = forms.ChoiceField(
        choices=[('', 'Todos los Estados')] + Order.STATUS_CHOICES,
        required=False,
        label="Estado del Pedido"
    )