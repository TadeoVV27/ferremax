# src/main.py
"""
API REST y Servidor Web FerreMax (FastAPI)
Incluye documentación interactiva Swagger (/docs) y Frontend de Mostrador/Caja.
"""

import os
import sys
import subprocess
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, status, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Asegurar path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.application.commands import (
    CrearCotizacionCommand, 
    AutorizarCreditoCommand
)
from src.domain.models import Cotizacion, Credito, Inventario, Pedido, Venta, Actor
from src.application.services import (
    VentaApplicationService,
    ValidacionApplicationService,
    InventarioApplicationService,
)
from src.infrastructure.persistence import (
    InMemoryVentaRepository,
    InMemoryCotizacionRepository,
    InMemoryInventarioRepository,
    InMemoryPedidoRepository,
    UnitOfWorkImpl,
)

# Inicializamos FastAPI con metadata completa
app = FastAPI(
    title="API FerreMax - Sistema de Mostrador y Caja",
    description="API REST y Sistema de Mostrador para ventas, crédito e inventario de FerreMax.",
    version="1.0.0"
)

# ----------------------------------------------------------------------------
# DEPENDENCIAS E INSTANCIAS DE SERVICIO (Clean Architecture)
# ----------------------------------------------------------------------------
venta_repo = InMemoryVentaRepository()
cotizacion_repo = InMemoryCotizacionRepository()
inventario_repo = InMemoryInventarioRepository()
pedido_repo = InMemoryPedidoRepository()
unit_of_work = UnitOfWorkImpl()

venta_service = VentaApplicationService(venta_repo, inventario_repo, unit_of_work)
validacion_service = ValidacionApplicationService(cotizacion_repo, unit_of_work)
inventario_service = InventarioApplicationService(inventario_repo, pedido_repo, unit_of_work)

# Catálogo ferretero con inventario enlazado
PRODUCTOS = [
    {
        "id": 1,
        "codigo": "CEM-001",
        "nombre": "Cemento Gris Tolteca 50kg",
        "categoria": "Material de Obra",
        "precio": 245.0,
        "unidad": "Bulto",
        "icono": "🧱",
        "inventario": Inventario(existencia=60, comprometido=5),
    },
    {
        "id": 2,
        "codigo": "VAR-038",
        "nombre": 'Varilla Corrugada 3/8" (12m)',
        "categoria": "Acero",
        "precio": 185.0,
        "unidad": "Pieza",
        "icono": "🏗️",
        "inventario": Inventario(existencia=120, comprometido=10),
    },
    {
        "id": 3,
        "codigo": "TAL-650",
        "nombre": 'Taladro Percutor 1/2" 650W Industrial',
        "categoria": "Herramienta Eléctrica",
        "precio": 1250.0,
        "unidad": "Pieza",
        "icono": "⚡",
        "inventario": Inventario(existencia=8, comprometido=0),
    },
    {
        "id": 4,
        "codigo": "PIN-019",
        "nombre": "Pintura Vinílica Blanca 19L ProMax",
        "categoria": "Acabados",
        "precio": 890.0,
        "unidad": "Cubeta",
        "icono": "🪣",
        "inventario": Inventario(existencia=15, comprometido=2),
    },
    {
        "id": 5,
        "codigo": "MAR-016",
        "nombre": "Martillo de Uña Curva 16oz Mango Fibra",
        "categoria": "Herramienta Manual",
        "precio": 165.0,
        "unidad": "Pieza",
        "icono": "🔨",
        "inventario": Inventario(existencia=30, comprometido=0),
    },
    {
        "id": 6,
        "codigo": "CAR-005",
        "nombre": "Carretilla Reforzada 5.5 ft³ Llanta Neumática",
        "categoria": "Carga y Transporte",
        "precio": 1450.0,
        "unidad": "Pieza",
        "icono": "🛒",
        "inventario": Inventario(existencia=5, comprometido=1),
    },
    {
        "id": 7,
        "codigo": "DIS-045",
        "nombre": 'Disco de Corte Metal 4-1/2" Extra Fino',
        "categoria": "Abrasivos",
        "precio": 28.0,
        "unidad": "Pieza",
        "icono": "💿",
        "inventario": Inventario(existencia=50, comprometido=0),
    },
    {
        "id": 8,
        "codigo": "CLA-025",
        "nombre": 'Clavo con Cabeza para Madera 2-1/2" (Caja 1kg)',
        "categoria": "Fijación",
        "precio": 48.0,
        "unidad": "Caja",
        "icono": "🔩",
        "inventario": Inventario(existencia=45, comprometido=0),
    },
]

for p in PRODUCTOS:
    inventario_repo.registrar_inventario(p["id"], p["inventario"])

COTIZACIONES_DEMO = [
    {
        "id": 101,
        "folio": "COT-101",
        "cliente": "Constructora Regia S.A. de C.V.",
        "monto": 34850.0,
        "vigente": True,
        "credito_autorizado": True,
        "descripcion": "50 Bultos de Cemento + 40 Varillas 3/8",
    },
    {
        "id": 102,
        "folio": "COT-102",
        "cliente": "Obras y Acabados del Norte",
        "monto": 12400.0,
        "vigente": False,
        "credito_autorizado": True,
        "descripcion": "8 Cubetas de Pintura + 12 Discos de Corte (VENCIDA HACE 4 DÍAS)",
    },
    {
        "id": 103,
        "folio": "COT-103",
        "cliente": "Juan Pérez (Contratista Independiente)",
        "monto": 8750.0,
        "vigente": True,
        "credito_autorizado": False,
        "descripcion": "2 Carretillas + 4 Taladros (CRÉDITO BLOQUEADO POR COBRANZA)",
    },
]

for cot in COTIZACIONES_DEMO:
    cotizacion_repo.guardar_cotizacion(
        Cotizacion(id_cotizacion=cot["id"], vigente=cot["vigente"])
    )

_contador_ventas = 1000
HISTORIAL_VENTAS = []

# ----------------------------------------------------------------------------
# CARTERA Y REGISTRO DE CLIENTES COMERCIALES (FerreMax CRM & DDD)
# ----------------------------------------------------------------------------
CLIENTES_REGISTRY = [
    {
        "id": "FER-C001",
        "nombre": "Constructora Regia S.A. de C.V.",
        "rfc": "CRE850315XX1",
        "tipo": "EMPRESARIAL",
        "es_preferente": True,
        "activo": True,
        "ciudad": "Monterrey",
        "telefono": "81-8340-2020",
        "limite_credito": 50000.0,
        "saldo_utilizado": 12400.0,
    },
    {
        "id": "FER-C002",
        "nombre": "Obras y Acabados del Norte",
        "rfc": "OAN920810AB2",
        "tipo": "CONTRATISTA",
        "es_preferente": False,
        "activo": True,
        "ciudad": "Apodaca",
        "telefono": "81-8311-5500",
        "limite_credito": 25000.0,
        "saldo_utilizado": 8750.0,
    },
    {
        "id": "FER-C003",
        "nombre": "Juan Pérez (Contratista Independiente)",
        "rfc": "PEPJ780415M12",
        "tipo": "CONTRATISTA",
        "es_preferente": False,
        "activo": True,
        "ciudad": "Monterrey",
        "telefono": "81-2233-4455",
        "limite_credito": 10000.0,
        "saldo_utilizado": 9500.0,
    },
    {
        "id": "FER-C005",
        "nombre": "Ferretería y Edificaciones El Roble",
        "rfc": "FER010203RO1",
        "tipo": "DISTRIBUIDOR",
        "es_preferente": True,
        "activo": True,
        "ciudad": "San Pedro Garza García",
        "telefono": "81-8899-7711",
        "limite_credito": 100000.0,
        "saldo_utilizado": 15000.0,
    },
    {
        "id": "FER-C007",
        "nombre": "Desarrollos Urbanos del Valle (Suspendido)",
        "rfc": "DUV991120XY9",
        "tipo": "EMPRESARIAL",
        "es_preferente": False,
        "activo": False,
        "ciudad": "Monterrey",
        "telefono": "81-8100-9900",
        "limite_credito": 30000.0,
        "saldo_utilizado": 30000.0,
    },
    {
        "id": "FER-C008",
        "nombre": "Instalaciones Eléctricas de Apodaca",
        "rfc": "IEA880620KL3",
        "tipo": "CONTRATISTA",
        "es_preferente": False,
        "activo": True,
        "ciudad": "Apodaca",
        "telefono": "81-8386-1122",
        "limite_credito": 20000.0,
        "saldo_utilizado": 4200.0,
    },
]

class ClienteCreateRequest(BaseModel):
    nombre: str
    rfc: Optional[str] = "XAXX010101000"
    tipo: Optional[str] = "EMPRESARIAL"
    es_preferente: bool = False
    activo: bool = True
    ciudad: str = "Monterrey"
    telefono: Optional[str] = "81-1234-5678"
    limite_credito: float = 15000.0



# ----------------------------------------------------------------------------
# ENDPOINTS REST EXISTENTES (CONSERVADOS DEL COMMIT DEL EQUIPO)
# ----------------------------------------------------------------------------
@app.post("/cotizaciones/", tags=["Cotizaciones"], status_code=status.HTTP_201_CREATED)
def crear_cotizacion(comando: CrearCotizacionCommand):
    """
    Registra una nueva cotización en el sistema.
    - **cliente_id**: Identificador numérico del cliente.
    - **productos_ids**: Lista con los identificadores de los productos.
    - **cantidades**: Lista con las cantidades a cotizar por producto.
    """
    return {"mensaje": "Comando de cotización recibido exitosamente", "datos": comando}


@app.post("/creditos/autorizar", tags=["Créditos"], status_code=status.HTTP_200_OK)
def autorizar_credito(comando: AutorizarCreditoCommand):
    """
    Procesa la autorización de crédito para un cliente.
    - Requiere el monto solicitado y el ID del cliente.
    - Internamente delegará la validación al ValidacionApplicationService.
    """
    return {"mensaje": "Solicitud de autorización en proceso", "cliente_id": comando.cliente_id}


# ----------------------------------------------------------------------------
# MODELOS PYDANTIC PARA EL FRONTEND DE MOSTRADOR
# ----------------------------------------------------------------------------
class VentaRequest(BaseModel):
    producto_id: int
    cantidad: int
    cliente_id: Optional[str] = "PUBLICO"


class ValidarCreditoRequest(BaseModel):
    id_cotizacion: int
    folio: str
    cliente: str
    vigente: bool
    credito_autorizado: bool

class FaltanteRequest(BaseModel):
    producto_id: int
    cantidad: int
    id_pedido: int = 501


# ----------------------------------------------------------------------------
# ENDPOINTS PARA EL FRONTEND FERRETERO
# ----------------------------------------------------------------------------
@app.get("/api/productos", tags=["Mostrador"])
def listar_productos():
    """Retorna el catálogo de productos con stock en tiempo real."""
    datos = []
    for p in PRODUCTOS:
        inv = p["inventario"]
        disponible = inv.existencia - inv.comprometido
        datos.append({
            "id": p["id"],
            "codigo": p["codigo"],
            "nombre": p["nombre"],
            "categoria": p["categoria"],
            "precio": p["precio"],
            "unidad": p["unidad"],
            "icono": p["icono"],
            "existencia": inv.existencia,
            "comprometido": inv.comprometido,
            "disponible": disponible,
        })
    return {"ok": True, "productos": datos}


@app.post("/api/venta/procesar", tags=["Mostrador"])
def procesar_venta(req: VentaRequest):
    """
    CU-01: Procesa una venta en mostrador usando VentaApplicationService.
    Aplica reglas de negocio:
    - Regla 1 (Specification): Valida que el cliente esté activo.
    - Regla 2 (Specification): Aplica descuento VIP si compra >= $1,500 MXN.
    - Descuenta inventario físico y confirma transacción en Unit of Work.
    """
    global _contador_ventas
    producto = next((p for p in PRODUCTOS if p["id"] == req.producto_id), None)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    if req.cantidad <= 0:
        raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a cero")

    # Identificar cliente asignado a la venta
    cliente_info = None
    cliente_nombre = "Público en General"
    es_vip = False
    if req.cliente_id and req.cliente_id != "PUBLICO":
        cliente_info = next((c for c in CLIENTES_REGISTRY if c["id"] == req.cliente_id), None)
        if cliente_info:
            cliente_nombre = cliente_info["nombre"]
            es_vip = cliente_info.get("es_preferente", False)

            # REGLA 1 (Specification Pattern): ActorActivo
            if not cliente_info.get("activo", True):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "mensaje": f"⛔ OPERACIÓN RECHAZADA: El cliente '{cliente_nombre}' se encuentra INACTIVO / SUSPENDIDO.",
                        "detalle": "Especificación de Dominio (PuedeProcesarseSpecification): Se requiere ActorActivo=Verdadero.",
                        "disponible": producto["inventario"].existencia - producto["inventario"].comprometido
                    }
                )

    inventario = producto["inventario"]
    _contador_ventas += 1
    id_venta = _contador_ventas
    venta = Venta(id_venta=id_venta)

    try:
        resultado = venta_service.procesar_venta_mostrador(venta, inventario, req.cantidad)
        subtotal = round(producto["precio"] * req.cantidad, 2)

        # REGLA 2 (Specification Pattern): Beneficio Preferente VIP si compra >= $1,500 MXN
        descuento_vip = 0.0
        mensaje_regla = "Precio regular de mostrador"
        if es_vip and subtotal >= 1500.0:
            descuento_vip = round(subtotal * 0.10, 2)  # 10% Descuento Preferente
            mensaje_regla = "⭐ Aplica Beneficio VIP (10% de descuento por compra >= $1,500 MXN)"
        elif es_vip:
            mensaje_regla = "Cliente VIP registrado (El descuento requiere compra mínima de $1,500 MXN)"

        total = round(subtotal - descuento_vip, 2)

        ticket = {
            "folio": f"VTA-{id_venta}",
            "fecha": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "producto": producto["nombre"],
            "codigo": producto["codigo"],
            "precio_unitario": producto["precio"],
            "cantidad": req.cantidad,
            "subtotal": subtotal,
            "descuento_vip": descuento_vip,
            "total": total,
            "cliente_id": req.cliente_id or "PUBLICO",
            "cliente": cliente_nombre,
            "es_vip": es_vip,
            "regla_aplicada": mensaje_regla,
            "estado": venta.estado,
            "stock_restante": inventario.existencia,
            "mensaje": resultado,
        }
        HISTORIAL_VENTAS.insert(0, ticket)
        return {
            "ok": True,
            "mensaje": "¡VENTA CONFIRMADA! Cobro registrado y entrega autorizada.",
            "ticket": ticket,
        }
    except ValueError as e:
        disponible = inventario.existencia - inventario.comprometido
        raise HTTPException(
            status_code=400,
            detail={
                "mensaje": f"NO SE PUEDE VENDER: {str(e)}",
                "detalle": f"Solicitaste {req.cantidad} {producto['unidad']}(s), pero en bodega solo hay {disponible} disponibles.",
                "disponible": disponible,
            }
        )


# ----------------------------------------------------------------------------
# ENDPOINTS GESTIÓN DE CLIENTES / CARTERA
# ----------------------------------------------------------------------------
@app.get("/api/clientes", tags=["Clientes"])
def listar_clientes():
    """Retorna la lista de clientes registrados con su crédito disponible y estado."""
    for c in CLIENTES_REGISTRY:
        c["credito_disponible"] = max(0.0, round(c["limite_credito"] - c.get("saldo_utilizado", 0.0), 2))
    return {
        "ok": True,
        "total": len(CLIENTES_REGISTRY),
        "clientes": CLIENTES_REGISTRY
    }


@app.post("/api/clientes", tags=["Clientes"], status_code=status.HTTP_201_CREATED)
def registrar_cliente(req: ClienteCreateRequest):
    """
    Registra un nuevo cliente/actor en la cartera comercial de FerreMax.
    Se sincroniza con el modelo de Dominio (Actor) y la máquina de especificaciones.
    """
    nombre_limpio = req.nombre.strip()
    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="El nombre del cliente no puede estar vacío")

    # Generar folio consecutivo
    num_id = len(CLIENTES_REGISTRY) + 1
    nuevo_id = f"FER-C{num_id:03d}"

    nuevo_cliente = {
        "id": nuevo_id,
        "nombre": nombre_limpio,
        "rfc": req.rfc.strip().upper() if req.rfc else "XAXX010101000",
        "tipo": req.tipo.strip().upper() if req.tipo else "EMPRESARIAL",
        "es_preferente": bool(req.es_preferente),
        "activo": bool(req.activo),
        "ciudad": req.ciudad.strip() if req.ciudad else "Monterrey",
        "telefono": req.telefono.strip() if req.telefono else "81-0000-0000",
        "limite_credito": float(req.limite_credito),
        "saldo_utilizado": 0.0,
        "credito_disponible": float(req.limite_credito),
    }
    CLIENTES_REGISTRY.append(nuevo_cliente)

    # Registrar en el Evaluador de Dominio (para compatibilidad con tests y especificaciones)
    try:
        actor_dominio = Actor(
            actor_id=nuevo_id,
            nombre=nombre_limpio,
            es_preferente=bool(req.es_preferente),
            activo=bool(req.activo),
            ciudad=req.ciudad.strip() if req.ciudad else "Monterrey"
        )
        evaluador_docente.actores[nuevo_id] = actor_dominio
    except Exception:
        pass

    return {
        "ok": True,
        "mensaje": f"¡Cliente '{nombre_limpio}' registrado con éxito en la cartera!",
        "cliente": nuevo_cliente
    }


@app.put("/api/clientes/{cliente_id}/toggle-activo", tags=["Clientes"])
def alternar_estado_cliente(cliente_id: str):
    """Alterna el estado Activo / Inactivo del cliente para validar la Regla 1 (Specification)."""
    cliente = next((c for c in CLIENTES_REGISTRY if c["id"] == cliente_id), None)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    cliente["activo"] = not cliente["activo"]
    if cliente_id in evaluador_docente.actores:
        evaluador_docente.actores[cliente_id].activo = cliente["activo"]

    estado_str = "ACTIVO" if cliente["activo"] else "INACTIVO / SUSPENDIDO"
    return {
        "ok": True,
        "mensaje": f"Estado de {cliente['nombre']} actualizado a {estado_str}",
        "activo": cliente["activo"]
    }


@app.put("/api/clientes/{cliente_id}/toggle-vip", tags=["Clientes"])
def alternar_vip_cliente(cliente_id: str):
    """Alterna el estado Preferente (VIP) para validar la Regla 2 (Specification)."""
    cliente = next((c for c in CLIENTES_REGISTRY if c["id"] == cliente_id), None)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    cliente["es_preferente"] = not cliente["es_preferente"]
    if cliente_id in evaluador_docente.actores:
        evaluador_docente.actores[cliente_id].es_preferente = cliente["es_preferente"]

    vip_str = "VIP / PREFERENTE" if cliente["es_preferente"] else "ESTÁNDAR"
    return {
        "ok": True,
        "mensaje": f"Categoría de {cliente['nombre']} actualizada a {vip_str}",
        "es_preferente": cliente["es_preferente"]
    }


@app.get("/api/cotizaciones", tags=["Créditos"])
def listar_cotizaciones():
    """Retorna las cotizaciones registradas para prueba rápida."""
    return {"ok": True, "cotizaciones": COTIZACIONES_DEMO}


@app.post("/api/credito/validar", tags=["Créditos"])
def validar_credito_cotizacion(req: ValidarCreditoRequest):
    """
    CU-03: Valida cotización vigente y crédito autorizado.
    """
    cotizacion = Cotizacion(id_cotizacion=req.id_cotizacion, vigente=req.vigente)
    cotizacion_repo.guardar_cotizacion(cotizacion)
    credito = Credito(autorizado=req.credito_autorizado)

    try:
        resultado = validacion_service.validar_operacion_credito(req.id_cotizacion, credito)
        return {
            "ok": True,
            "autorizado": True,
            "mensaje": "✅ OPERACIÓN AUTORIZADA PARA DESPACHO A CRÉDITO",
            "detalle": f"La cotización {req.folio} está vigente y la línea de crédito para {req.cliente} fue aprobada con éxito.",
        }
    except ValueError as e:
        err = str(e)
        if "vencida" in err.lower():
            titulo = "⛔ OPERACIÓN DETENIDA: COTIZACIÓN VENCIDA"
            detalle = f"La cotización {req.folio} ha caducado. El cliente debe solicitar una re-cotización con precios actualizados."
        else:
            titulo = "⛔ OPERACIÓN RECHAZADA: CRÉDITO NO AUTORIZADO"
            detalle = f"El departamento de crédito/cobranza no autorizó la operación a {req.cliente}. Solicitar pago de contado."
        
        raise HTTPException(
            status_code=400,
            detail={"mensaje": titulo, "detalle": detalle}
        )


@app.post("/api/almacen/gestionar-faltante", tags=["Almacén"])
def gestionar_faltante(req: FaltanteRequest):
    """
    CU-04: Gestiona faltante de inventario. Si no alcanza, marca pedido como Parcial.
    """
    producto = next((p for p in PRODUCTOS if p["id"] == req.producto_id), None)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    inventario = producto["inventario"]
    pedido = Pedido(id_pedido=req.id_pedido, estado="Pendiente")
    pedido_repo.guardar_pedido(pedido)

    resultado = inventario_service.gestionar_faltante_inventario(inventario, req.cantidad, pedido)
    disponible = inventario.existencia - inventario.comprometido
    es_parcial = pedido.estado == "Parcial"

    return {
        "ok": True,
        "mensaje": resultado,
        "estado_pedido": pedido.estado,
        "es_parcial": es_parcial,
        "solicitado": req.cantidad,
        "disponible_actual": disponible,
        "detalle": (
            f"Pedido #{req.id_pedido} marcado como PARCIAL. Solo se pueden entregar {disponible} piezas. "
            f"Se generó solicitud de transferencia para el resto."
            if es_parcial
            else f"Inventario suficiente para surtir las {req.cantidad} piezas completas."
        ),
    }


@app.get("/api/ventas/historial", tags=["Mostrador"])
def historial_ventas():
    return {"ok": True, "ventas": HISTORIAL_VENTAS}


from src.application.evaluador_docente import EvaluadorDocenteService
from src.domain.state_machine import TransicionEstadoInvalidaException

# Evaluador del dataset oficial
DATA_DIR = os.path.join(BASE_DIR, "data")
evaluador_docente = EvaluadorDocenteService(DATA_DIR)
if os.path.exists(DATA_DIR):
    try:
        evaluador_docente.cargar_datos()
    except Exception as _e:
        pass


@app.post("/api/docente/procesar-csvs", tags=["PIA Evaluador Oficial"])
def procesar_csvs_desde_cero():
    """
    Carga y procesa todos los datasets CSV oficiales desde cero:
    1. Lee actores, catálogo, operaciones y detalles.
    2. Calcula los importes totales con Decimal.
    3. Evalúa los 120 casos de prueba (Specification Pattern).
    4. Evalúa las 20 pruebas de transición (State Machine Pattern).
    5. Genera los archivos 'casos_prueba_resueltos.csv' y 'transiciones_prueba_resueltas.csv'.
    """
    try:
        evaluador_docente.cargar_datos()
        casos = evaluador_docente.resolver_casos_prueba(guardar_archivo=True)
        trans = evaluador_docente.resolver_transiciones_prueba(guardar_archivo=True)
        return {
            "ok": True,
            "mensaje": "Datasets procesados exitosamente desde cero",
            "actores_cargados": len(evaluador_docente.actores),
            "articulos_catalogo": len(evaluador_docente.recursos),
            "operaciones_cargadas": len(evaluador_docente.operaciones),
            "casos_prueba_resueltos": len(casos),
            "transiciones_resueltas": len(trans),
            "archivos_generados": [
                "data/casos_prueba_resueltos.csv",
                "data/transiciones_prueba_resueltas.csv"
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/docente/casos", tags=["PIA Evaluador Oficial"])
def obtener_casos_docente():
    """Retorna los 120 casos de prueba del docente resueltos con el patrón Specification."""
    try:
        casos = evaluador_docente.resolver_casos_prueba(guardar_archivo=False)
        return {"ok": True, "total": len(casos), "casos": casos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/docente/transiciones", tags=["PIA Evaluador Oficial"])
def obtener_transiciones_docente():
    """Retorna las 20 pruebas de transición evaluadas con la State Machine."""
    try:
        trans = evaluador_docente.resolver_transiciones_prueba(guardar_archivo=False)
        return {"ok": True, "total": len(trans), "transiciones": trans}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/operaciones/{operacion_id}/transicion", tags=["Máquina de Estados"])
def ejecutar_transicion_operacion(operacion_id: str, accion: str):
    """
    Ejecuta una acción sobre una Operación y dispara eventos de dominio.
    Acciones válidas: 'aprobar', 'surtir', 'entregar', 'completar', 'cancelar'.
    """
    op = evaluador_docente.operaciones.get(operacion_id)
    if not op:
        raise HTTPException(status_code=404, detail=f"Operación '{operacion_id}' no encontrada")

    try:
        if accion == "aprobar":
            op.aprobar()
        elif accion == "surtir":
            op.surtir()
        elif accion == "entregar":
            op.entregar()
        elif accion == "completar":
            op.completar()
        elif accion == "cancelar":
            op.cancelar()
        else:
            raise HTTPException(status_code=400, detail=f"Acción '{accion}' no soportada")

        return {
            "ok": True,
            "operacion_id": operacion_id,
            "nuevo_estado": op.estado,
            "eventos_emitidos": [e.nombre_evento() for e in op.eventos],
        }
    except TransicionEstadoInvalidaException as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Transición de estado inválida",
                "estado_actual": e.estado_actual,
                "accion": e.accion,
                "motivo": e.motivo,
            }
        )


@app.post("/api/pruebas/ejecutar", tags=["Auditoría"])
def ejecutar_pruebas():
    """Ejecuta pytest en el servidor y retorna el resultado."""
    test_path = os.path.join(BASE_DIR, "tests")
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=BASE_DIR,
        )
        return {
            "ok": res.returncode == 0,
            "salida": res.stdout + "\n" + res.stderr,
            "exito": res.returncode == 0,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ----------------------------------------------------------------------------
# RUTA RAÍZ: FRONTEND DEL MOSTRADOR FERRETERO
# ----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, tags=["Interfaz"])
def frontend_mostrador():
    """Entrega la interfaz gráfica para el trabajador de FerreMax."""
    html_path = os.path.join(BASE_DIR, "templates", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>FerreMax: templates/index.html no encontrado</h1>"


if __name__ == "__main__":
    import uvicorn
    print("=" * 65)
    print(" 🛠️  FERREMAX POS - SISTEMA DE MOSTRADOR Y CAJA (FASTAPI) 🛠️")
    print("=" * 65)
    print(" -> Mostrador: http://localhost:8000")
    print(" -> Documentación Swagger API: http://localhost:8000/docs")
    print("=" * 65)
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
