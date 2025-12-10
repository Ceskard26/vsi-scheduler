#!/usr/bin/env python3
import os
import sys
from ibm_vpc import VpcV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_cloud_sdk_core import ApiException

# =============================================================================
# CONFIGURACIÓN - Los clientes deben configurar estas variables de entorno
# =============================================================================

# API Key de IBM Cloud (OBLIGATORIO)
# Los clientes deben crear su propia API Key en: https://cloud.ibm.com/iam/apikeys
API_KEY = os.getenv('IBM_API_KEY')

# Lista de IDs de instancias separadas por comas (OBLIGATORIO)
# Ejemplo: "0757_abc123,0757_def456,0757_ghi789"
# Los clientes obtienen estos IDs con: ibmcloud is instances
INSTANCE_IDS = os.getenv('INSTANCE_IDS', '')

# Región de IBM Cloud (OBLIGATORIO)
# Valores comunes: us-south, us-east, eu-de, eu-gb, jp-tok, au-syd
# Los clientes deben especificar su región
REGION = os.getenv('REGION', 'us-east')

# Acción a ejecutar: start, stop, o status (OBLIGATORIO)
# Los clientes configuran esto según el job (start o stop)
ACTION = os.getenv('ACTION', 'status')

# Modo de ejecución: sequential o parallel (OPCIONAL)
# sequential: procesa instancias una por una
# parallel: procesa todas simultáneamente (más rápido pero menos control)
EXECUTION_MODE = os.getenv('EXECUTION_MODE', 'sequential')

# Continuar en caso de error (OPCIONAL)
# Si es 'true', continúa con las demás instancias si una falla
# Si es 'false', detiene la ejecución al primer error
CONTINUE_ON_ERROR = os.getenv('CONTINUE_ON_ERROR', 'true').lower() == 'true'

# =============================================================================
# FIN DE CONFIGURACIÓN
# =============================================================================

def get_vpc_service():
    """Inicializa el servicio VPC con autenticación"""
    authenticator = IAMAuthenticator(API_KEY)
    vpc_service = VpcV1(authenticator=authenticator)
    vpc_service.set_service_url(f'https://{REGION}.iaas.cloud.ibm.com/v1')
    return vpc_service

def get_instance_status(vpc_service, instance_id):
    """Obtiene el estado actual de una instancia"""
    try:
        instance = vpc_service.get_instance(id=instance_id).get_result()
        return instance['status'], instance.get('name', 'Unknown')
    except ApiException as e:
        print(f"❌ Error obteniendo estado de {instance_id}: {e}")
        return None, None

def start_instance(vpc_service, instance_id):
    """Inicia una instancia"""
    try:
        status, name = get_instance_status(vpc_service, instance_id)
        if status is None:
            return False
        
        if status == 'running':
            print(f"ℹ️  Instancia {name} ({instance_id[:13]}...) ya está en ejecución")
            return True
        
        print(f"▶️  Iniciando instancia {name} ({instance_id[:13]}...)...")
        vpc_service.create_instance_action(
            instance_id=instance_id,
            type='start'
        )
        print(f"✓ Comando de inicio enviado exitosamente para {name}")
        return True
    except ApiException as e:
        print(f"❌ Error iniciando instancia {instance_id}: {e}")
        return False

def stop_instance(vpc_service, instance_id):
    """Detiene una instancia"""
    try:
        status, name = get_instance_status(vpc_service, instance_id)
        if status is None:
            return False
        
        if status == 'stopped':
            print(f"ℹ️  Instancia {name} ({instance_id[:13]}...) ya está detenida")
            return True
        
        print(f"⏸️  Deteniendo instancia {name} ({instance_id[:13]}...)...")
        vpc_service.create_instance_action(
            instance_id=instance_id,
            type='stop'
        )
        print(f"✓ Comando de detención enviado exitosamente para {name}")
        return True
    except ApiException as e:
        print(f"❌ Error deteniendo instancia {instance_id}: {e}")
        return False

def show_status(vpc_service, instance_id):
    """Muestra el estado de una instancia"""
    try:
        status, name = get_instance_status(vpc_service, instance_id)
        if status is None:
            return False
        
        status_emoji = {
            'running': '🟢',
            'stopped': '🔴',
            'stopping': '🟡',
            'starting': '🟡',
            'pending': '🟡'
        }.get(status, '⚪')
        
        print(f"{status_emoji} {name} ({instance_id[:13]}...): {status}")
        return True
    except ApiException as e:
        print(f"❌ Error obteniendo estado de {instance_id}: {e}")
        return False

def process_instances_sequential(vpc_service, instance_ids, action_func):
    """Procesa instancias secuencialmente"""
    results = {'success': 0, 'failed': 0, 'total': len(instance_ids)}
    
    for instance_id in instance_ids:
        success = action_func(vpc_service, instance_id)
        if success:
            results['success'] += 1
        else:
            results['failed'] += 1
            if not CONTINUE_ON_ERROR:
                print("\n⚠️  Deteniendo ejecución debido a un error")
                break
    
    return results

def process_instances_parallel(vpc_service, instance_ids, action_func):
    """Procesa instancias en paralelo usando threads"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    results = {'success': 0, 'failed': 0, 'total': len(instance_ids)}
    
    with ThreadPoolExecutor(max_workers=min(10, len(instance_ids))) as executor:
        future_to_instance = {
            executor.submit(action_func, vpc_service, instance_id): instance_id 
            for instance_id in instance_ids
        }
        
        for future in as_completed(future_to_instance):
            instance_id = future_to_instance[future]
            try:
                success = future.result()
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            except Exception as e:
                print(f"❌ Error procesando {instance_id}: {e}")
                results['failed'] += 1
    
    return results

def main():
    print("=" * 70)
    print("IBM Cloud VPC Instance Scheduler - Multi-Instance")
    print("=" * 70)
    
    # Validar configuración
    if not API_KEY:
        print("❌ Error: IBM_API_KEY no está configurada")
        print("Los clientes deben configurar esta variable con su API Key")
        sys.exit(1)
    
    if not INSTANCE_IDS:
        print("❌ Error: INSTANCE_IDS no está configurada")
        print("Los clientes deben configurar esta variable con IDs separados por comas")
        print("Ejemplo: INSTANCE_IDS='0757_abc123,0757_def456'")
        sys.exit(1)
    
    # Parsear IDs de instancias
    instance_ids = [id.strip() for id in INSTANCE_IDS.split(',') if id.strip()]
    
    if not instance_ids:
        print("❌ Error: No se encontraron IDs de instancias válidos")
        sys.exit(1)
    
    # Mostrar configuración
    print(f"\n📋 Configuración:")
    print(f"   Región: {REGION}")
    print(f"   Acción: {ACTION}")
    print(f"   Instancias: {len(instance_ids)}")
    print(f"   Modo: {EXECUTION_MODE}")
    print(f"   Continuar en error: {CONTINUE_ON_ERROR}")
    print(f"\n🖥️  Instancias a procesar:")
    for idx, instance_id in enumerate(instance_ids, 1):
        print(f"   {idx}. {instance_id}")
    print("-" * 70)
    
    # Inicializar servicio VPC
    vpc_service = get_vpc_service()
    
    # Seleccionar función según acción
    action_map = {
        'start': start_instance,
        'stop': stop_instance,
        'status': show_status
    }
    
    if ACTION not in action_map:
        print(f"❌ Acción no válida: {ACTION}")
        print(f"Acciones válidas: {', '.join(action_map.keys())}")
        sys.exit(1)
    
    action_func = action_map[ACTION]
    
    # Procesar instancias
    print(f"\n🚀 Procesando instancias en modo {EXECUTION_MODE}...\n")
    
    if EXECUTION_MODE == 'parallel':
        results = process_instances_parallel(vpc_service, instance_ids, action_func)
    else:
        results = process_instances_sequential(vpc_service, instance_ids, action_func)
    
    # Mostrar resumen
    print("\n" + "=" * 70)
    print("📊 Resumen de ejecución:")
    print(f"   Total: {results['total']}")
    print(f"   ✓ Exitosas: {results['success']}")
    print(f"   ✗ Fallidas: {results['failed']}")
    print("=" * 70)
    
    # Exit code basado en resultados
    if results['failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
