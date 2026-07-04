from fastapi import FastAPI, Request, status, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional, List
from enum import Enum
from datetime import date, datetime
import http

app = FastAPI()


class CarrierStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class WorkShift(str, Enum):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    NIGHT = "NIGHT"


T = TypeVar("T")


class EnvelopeResponse(BaseModel, Generic[T]):
    statusCode: int
    message: str
    data: Optional[T] = None
    error: Optional[T] = None
    timestamp: str
    path: str


def success_response(
    request: Request,
    data: T = None,
    message: str = "Thành công",
    code: int = status.HTTP_200_OK,
):
    return {
        "statusCode": code,
        "message": message,
        "data": data,
        "error": None,
        "timestamp": datetime.now().isoformat(),
        "path": request.url.path,
    }


# ==========================================
# EXCEPTION HANDLERS (BẪY LỖI)
# ==========================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "statusCode": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "message": "Dữ liệu đầu vào không hợp lệ",
            "data": None,
            "error": http.HTTPStatus(422).phrase,
            "timestamp": datetime.now().isoformat(),
            "path": request.url.path,
        },
    )


# Vẫn giữ StarletteHTTPException ở đây để tóm gọn CẢ lỗi của FastAPI và lỗi ngầm của framework
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "statusCode": exc.status_code,
            "message": exc.detail,
            "data": None,
            "error": http.HTTPStatus(exc.status_code).phrase,
            "timestamp": datetime.now().isoformat(),
            "path": request.url.path,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "statusCode": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": "Hệ thống gặp sự cố nội bộ",
            "data": None,
            "error": http.HTTPStatus(500).phrase,
            "timestamp": datetime.now().isoformat(),
            "path": request.url.path,
        },
    )


# ==========================================
# SCHEMAS & DATABASE (MOCK)
# ==========================================


class CarrierCreate(BaseModel):
    code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=3)
    max_weight_capacity: int = Field(..., gt=0)
    status: CarrierStatus


class ShipmentCreate(BaseModel):
    carrier_id: int
    order_reference: str = Field(..., min_length=1)
    total_weight: int = Field(..., gt=0)  # Đã sửa lỗi đánh máy = int = thành : int =
    dispatch_date: date
    shift: WorkShift


carriers_db = [
    {
        "id": 1,
        "code": "GHN",
        "name": "Giao Hang Nhanh",
        "max_weight_capacity": 5000,
        "status": "ACTIVE",
    },
    {
        "id": 2,
        "code": "GHTK",
        "name": "Giao Hang Tiet Kiem",
        "max_weight_capacity": 3000,
        "status": "ACTIVE",
    },
    {
        "id": 3,
        "code": "VTP",
        "name": "Viettel Post",
        "max_weight_capacity": 10000,
        "status": "SUSPENDED",
    },
]

shipments_db = [
    {
        "id": 1,
        "carrier_id": 1,
        "order_reference": "ORD-2026-001",
        "total_weight": 4200,
        "dispatch_date": "2026-07-01",
        "shift": "MORNING",
    }
]


def get_carrier_by_id(carrier_id: int):
    return next((c for c in carriers_db if c.get("id") == carrier_id), None)


def get_carrier_by_code(carrier_code: str):
    return next(
        (c for c in carriers_db if c.get("code").upper() == carrier_code.upper()), None
    )


# ==========================================
# ROUTES
# ==========================================


@app.post("/carriers", response_model=EnvelopeResponse[dict])
def create_carrier(carrier: CarrierCreate, request: Request):
    if get_carrier_by_code(carrier.code):
        # Dùng HTTPException của FastAPI để ném lỗi
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Mã đối tác đã tồn tại"
        )

    new_id = 1 if not carriers_db else max(c["id"] for c in carriers_db) + 1

    new_carrier = {"id": new_id, **carrier.model_dump()}
    carriers_db.append(new_carrier)

    return success_response(
        request,
        data=new_carrier,
        message="Thêm đối tác thành công",
        code=status.HTTP_201_CREATED,
    )


# Đã fix Response Model thành List[dict]
@app.get("/carriers", response_model=EnvelopeResponse[List[dict]])
def get_all_carriers(
    request: Request,
    keyword: Optional[str] = None,
    status_query: Optional[
        CarrierStatus
    ] = None,  # Đổi tên biến để tránh nhầm với thư viện 'status'
    min_weight: Optional[int] = Query(None, gt=0),
):
    filtered_carriers = carriers_db

    if keyword:
        kw = keyword.lower().strip()
        filtered_carriers = [
            c
            for c in filtered_carriers
            if kw in c.get("code").lower() or kw in c.get("name").lower()
        ]

    if status_query:
        filtered_carriers = [
            c for c in filtered_carriers if c.get("status") == status_query.value
        ]

    if min_weight is not None:
        filtered_carriers = [
            c for c in filtered_carriers if c.get("max_weight_capacity") >= min_weight
        ]

    return success_response(
        request, data=filtered_carriers, message="Lấy danh sách đối tác thành công"
    )


@app.get("/carriers/{carrier_id}")
def get_carrier(carrier_id: int, request: Request):
    carrier = get_carrier_by_id(carrier_id)

    if not carrier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Carrier not found"
        )

    return success_response(request, data=carrier, message="Tìm thấy đối tác")


@app.put("/carriers/{carrier_id}", response_model=EnvelopeResponse)
def update_carrier(carrier_id: int, carrier: CarrierCreate, request: Request):
    target_carrier = get_carrier_by_id(carrier_id)
    if not target_carrier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Carrier not found"
        )

    is_duplicate = any(
        c.get("code").upper() == carrier.code.upper() and c.get("id") != carrier_id
        for c in carriers_db
    )

    if is_duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Mã đối tác đã tồn tại"
        )

    target_carrier.update(carrier.model_dump())

    return success_response(
        request, data=target_carrier, message="Đã update đối tác thành công"
    )


@app.delete("/carriers/{carrier_id}", response_model=EnvelopeResponse[dict])
def delete_carrier(carrier_id: int, request: Request):
    target_carrier = get_carrier_by_id(carrier_id)
    if not target_carrier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Carrier not found"
        )

    carriers_db.remove(target_carrier)
    return success_response(request, message="Xóa đối tác thành công")


@app.post("/shipments", response_model=EnvelopeResponse[dict])
def create_shipment(shipment: ShipmentCreate, request: Request):
    target_carrier = get_carrier_by_id(shipment.carrier_id)
    if not target_carrier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Carrier not found"
        )

    if target_carrier.get("status") != CarrierStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đối tác đang không hoạt động",
        )

    if shipment.total_weight > target_carrier.get("max_weight_capacity"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quá tải: Chuyến hàng ({shipment.total_weight}kg) vượt năng lực đối tác ({target_carrier.get('max_weight_capacity')}kg)",
        )

    is_conflict = any(
        s.get("carrier_id") == shipment.carrier_id
        and s.get("dispatch_date") == shipment.dispatch_date.isoformat()
        and s.get("shift") == shipment.shift.value
        for s in shipments_db
    )

    if is_conflict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đối tác đã được gán một chuyến hàng khác trong cùng ca và ngày này",
        )

    new_id = 1 if not shipments_db else max(s["id"] for s in shipments_db) + 1

    # Khởi tạo siêu gọn gàng nhờ Pydantic mode='json'
    new_shipment = {"id": new_id, **shipment.model_dump(mode="json")}
    shipments_db.append(new_shipment)

    return success_response(
        request,
        data=new_shipment,
        message="Khởi tạo chuyến hàng thành công",
        code=status.HTTP_201_CREATED,
    )


@app.get("/shipments", response_model=EnvelopeResponse[List[dict]])
def get_all_shipments(request: Request):
    return success_response(
        request, data=shipments_db, message="Lấy danh sách chuyến hàng thành công"
    )
