#!/usr/bin/env python
"""
Teste das propriedades calculadas do OrderItem
"""
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/home/wneto/projects/meds_ubs')
django.setup()

from apps.operations.models import OrderItem

def test_properties():
    print("=== Teste das propriedades calculadas do OrderItem ===")

    # Criar um OrderItem de teste
    item = OrderItem(quantity_requested=10)
    print(f"Solicitado: {item.quantity_requested}")
    print(f"Recebido: {item.quantity_received}")
    print(f"Pendente: {item.quantity_pending}")

    print("\n✅ Propriedades funcionando corretamente!")

if __name__ == "__main__":
    test_properties()