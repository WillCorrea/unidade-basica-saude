#!/usr/bin/env python3
import re

with open('apps/operations/services/order_service.py', 'r') as f:
    content = f.read()

content = re.sub(r'StockMovement\.TYPE_IN', 'StockMovement.TYPE_ENTRY', content)

with open('apps/operations/services/order_service.py', 'w') as f:
    f.write(content)

print('Correção aplicada')