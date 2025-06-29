from django.db import models
from django.urls import reverse
import random
import string
from decimal import Decimal
import secrets
import uuid 

class Customer(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    customer_code = models.CharField(max_length=4, unique=True, blank=True)
    qr_code = models.ImageField(upload_to='customer_qr_codes/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def generate_customer_code(self):
        """Genera un código único de 4 dígitos."""
        while True:
            code = ''.join(random.choices(string.digits, k=4))
            if not Customer.objects.filter(customer_code=code).exists():
                return code

    def generate_qr_code(self):
        """Genera un QR que apunta a la vista pública del cliente."""
        import qrcode
        from django.core.files import File
        from io import BytesIO

        qr_url = reverse('customer_status', args=[self.customer_code])
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(f"http://localhost:8000{qr_url}")
        qr.make(fit=True)

        img = qr.make_image(fill='black', back_color='white')
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        self.qr_code.save(f"qr_customer_{self.customer_code}.png", File(buffer), save=True)

    def save(self, *args, **kwargs):
        """Genera el código y el QR al guardar el cliente."""
        if not self.customer_code:
            self.customer_code = self.generate_customer_code()
        if not self.qr_code:
            self.generate_qr_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (ID: {self.customer_code})"

class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
    

def generate_short_id():
    """
    Esta es nuestra 'máquina'.
    Crea un código aleatorio de 8 caracteres.
    Usa letras (mayúsculas y minúsculas) y números.
    """
    # 1. Define el alfabeto que usaremos.
    alphabet = string.ascii_letters + string.digits

    # 2. Inicia un bucle infinito (se romperá cuando encontremos un código único).
    while True:
        # 3. Crea un código aleatorio de 8 caracteres.
        short_id = ''.join(secrets.choice(alphabet) for i in range(8))
        
        # 4. Revisa en la base de datos si este código ya existe en algún otro pedido.
        if not Order.objects.filter(short_id=short_id).exists():
            # 5. Si NO existe, ¡genial! Devolvemos el código y terminamos.
            return short_id

class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre de la Categoría")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")

    class Meta:
        verbose_name = "Categoría de Producto"
        verbose_name_plural = "Categorías de Productos"

    def __str__(self):
        return self.name

class Order(models.Model):
    STATUS_CHOICES = [
        ('PROCESSING', 'En proceso'),
        ('READY', 'Listo para recoger'),
        # --- LÍNEA AÑADIDA ---
        ('DELIVERED', 'Entregado'), 
        ('CANCELLED', 'Anulado'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Efectivo'),
        ('YAPE', 'Yape'),
        ('PLIN', 'Plin'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Falta Pagar'),
        ('PAID', 'Pagado'),
        ('PARTIAL', 'Parcialmente Pagado'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    order_code = models.CharField(max_length=10, unique=True, blank=True, null=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # Peso en kg
    total_weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Campo técnico para resolver error de constraint.")

    weight_price_per_kg = models.DecimalField(max_digits=10, decimal_places=2, default=5.00)  # Precio por kg
    categories = models.ManyToManyField(Category, through='OrderCategory')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PROCESSING')
    short_id = models.CharField(max_length=8, blank=True, unique=True, editable=False)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='CASH')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    payment_proof = models.ImageField(upload_to='payment_proofs/', blank=True, null=True)
    partial_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # Monto pagado parcialmente
    notes = models.TextField(blank=True, null=True)  # Campo de notas
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    original_calculated_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text='Precio calculado automáticamente basado en el peso y categorías.')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text='Monto de descuento aplicado al pedido.')
    price_adjusted_by_user = models.BooleanField(default=False, help_text='Indica si el precio final fue ajustado manualmente por un usuario.')

    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name="Código de Barras (SKU)")
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Categoría de Producto")

    def save(self, *args, **kwargs):
        # Esta línea mágica pregunta: "¿Este pedido es nuevo y no tiene un short_id?"
        if not self.short_id:
            # Si la respuesta es sí, llama a nuestra "máquina" para que le genere uno.
            self.short_id = generate_short_id()
        # Finalmente, guarda el pedido (con su nuevo código si era nuevo).
        super().save(*args, **kwargs)

    def generate_order_code(self):
        """Genera un código único de 6 caracteres para el pedido."""
        length = 6
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
            if not Order.objects.filter(order_code=code).exists():
                return code

    def calculate_initial_price(self):
        """Calcula el precio basado en los artículos y el peso. Este método ya no se usa directamente para el precio final."""
        weight_price = (self.weight or 0) * self.weight_price_per_kg
        category_price = sum(item.quantity * item.category.price for item in self.ordercategory_set.all())
        return Decimal(weight_price) + Decimal(category_price)

    @property
    def total_price(self):
        """Devuelve el precio final del pedido, considerando los ajustes."""
        if self.price_adjusted_by_user:
            final_price = self.original_calculated_price - self.discount_amount
            return final_price.quantize(Decimal('0.01'))
        # Para pedidos nuevos o antiguos sin ajuste, devuelve el precio calculado original.
        return self.original_calculated_price.quantize(Decimal('0.01'))
    
    @property
    def weight_total_price(self):
        """Calcula el precio solo para el peso."""
        return (self.weight or 0) * self.weight_price_per_kg

    def remaining_amount(self):
            """
            Calcula el monto restante.
            Usa `self.total_price` como una propiedad (sin paréntesis).
            """
            # Obtenemos el precio final usando la propiedad
            final_price = self.total_price 
            
            if self.payment_status == 'PARTIAL':
                return final_price - self.partial_amount
            elif self.payment_status == 'PENDING':
                return final_price
            else: # Si está 'PAID' o cualquier otro estado.
                return Decimal('0.00')

    def generate_qr_code(self):
        import qrcode
        from django.core.files import File
        from io import BytesIO

        qr_url = reverse('order_status', args=[self.id])
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(f"http://localhost:8000{qr_url}")
        qr.make(fit=True)

        img = qr.make_image(fill='black', back_color='white')
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        self.qr_code.save(f"qr_{self.id}.png", File(buffer), save=True)

    def __str__(self):
        return f"Pedido {self.id} - {self.customer.name}"

class OrderCategory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    @property
    def price(self):
        """Calcula el precio total para esta línea de categoría."""
        return self.quantity * self.category.price

    def __str__(self):
        return f"{self.category.name} x{self.quantity} (Pedido {self.order.id})"
    
class AppConfiguration(models.Model):
    key = models.CharField(max_length=50, primary_key=True)
    value = models.CharField(max_length=255)

    def __str__(self):
        return self.key

    # Para asegurar que solo haya una instancia de cada ajuste
    class Meta:
        verbose_name_plural = "Configuraciones de la Aplicación"

# === INICIO DE CÓDIGO AÑADIDO ===

class Product(models.Model):
    """Representa un producto que se puede vender en la tienda."""
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Producto")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de Venta")
    stock = models.PositiveIntegerField(default=0, verbose_name="Cantidad en Stock")
    image = models.ImageField(upload_to='product_images/', blank=True, null=True, verbose_name="Imagen del Producto")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} (Stock: {self.stock})"

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"


class Sale(models.Model):
    """Representa una transacción de venta de productos."""
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Cliente")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Monto Total")
    created_at = models.DateTimeField(auto_now_add=True)

# <--- CAMBIO: AÑADIMOS CAMPOS DE PAGO --->
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Efectivo'),
        ('YAPE', 'Yape'),
        ('PLIN', 'Plin'),
        ('CARD', 'Tarjeta'), # Añadimos Tarjeta como opción
    ]
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='CASH', verbose_name="Método de Pago")
    payment_status = models.CharField(max_length=20, choices=[('PAID', 'Pagado'), ('PENDING', 'Pendiente')], default='PAID', verbose_name="Estado del Pago")


    def __str__(self):
        customer_name = self.customer.name if self.customer else "Venta de Mostrador"
        return f"Venta #{self.id} - {customer_name}"

    def calculate_total(self):
        """Calcula el total de la venta a partir de sus artículos."""
        total = sum(item.quantity * item.unit_price for item in self.saleitem_set.all())
        self.total_amount = total
        self.save()

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"


class SaleItem(models.Model):
    """Representa un artículo dentro de una venta."""
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, verbose_name="Venta")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="Producto")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Cantidad")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Unitario")

    def __str__(self):
        return f"{self.quantity} x {self.product.name} en Venta #{self.sale.id}"

    def save(self, *args, **kwargs):
        # Guarda el precio del producto al momento de la venta
        if not self.unit_price:
            self.unit_price = self.product.price
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Artículo de Venta"
        verbose_name_plural = "Artículos de Venta"
# === FIN DE CÓDIGO AÑADIDO ===
# Es buena práctica poner las funciones auxiliares cerca de donde se usan
def generate_short_id():
    """Genera un ID aleatorio y seguro de 8 caracteres."""
    alphabet = string.ascii_letters + string.digits
    while True:
        # Creamos un ID aleatorio usando la librería secrets (más segura)
        short_id = ''.join(secrets.choice(alphabet) for _ in range(8))
        # Verificamos que este ID no exista ya en la base de datos para evitar colisiones
        if not Order.objects.filter(short_id=short_id).exists():
            return short_id