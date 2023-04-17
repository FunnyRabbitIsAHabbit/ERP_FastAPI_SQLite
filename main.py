import inspect
from typing import List
from typing import Type

from fastapi import FastAPI, Depends, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic.fields import ModelField
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


def as_form(cls: Type[BaseModel]):
    new_parameters = []

    for field_name, model_field in cls.__fields__.items():
        model_field: ModelField  # type: ignore

        new_parameters.append(
            inspect.Parameter(
                model_field.alias,
                inspect.Parameter.POSITIONAL_ONLY,
                default=Form(...) if model_field.required else Form(model_field.default),
                annotation=model_field.outer_type_,
            )
        )

    async def as_form_func(**data):
        return cls(**data)

    sig = inspect.signature(as_form_func)
    sig = sig.replace(parameters=new_parameters)
    as_form_func.__signature__ = sig  # type: ignore
    setattr(cls, 'as_form', as_form_func)

    return cls


app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods="*",
    allow_headers=["*"],
)

engine = create_engine('sqlite:///inventory.db')
Session = sessionmaker(bind=engine)
Base = declarative_base()


def get_session():
    session = Session()
    try:
        yield session
    finally:
        session.close()


class Product(Base):
    __tablename__ = 'products'
    _id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)
    price = Column(Float)
    quantity = Column(Integer)

    @property
    def id(self):
        return self._id


class BetterBaseModel(BaseModel):
    class Config:
        orm_mode = True


@as_form
class ProductInput(BetterBaseModel):
    name: str
    description: str
    price: float
    quantity: int


@as_form
class ProductOutput(BetterBaseModel):
    _id: int
    name: str
    description: str
    price: float
    quantity: int


@app.post("/products/", response_model=ProductOutput)
def create_product(product: ProductInput = Depends(ProductInput.as_form), session: Session = Depends(get_session)):
    db_product = Product(name=product.name, description=product.description, price=product.price,
                         quantity=product.quantity)
    session.add(db_product)
    session.commit()
    session.refresh(db_product)
    return db_product


@app.get("/products/", response_model=List[ProductOutput])
def get_products(session: Session = Depends(get_session)):
    products = session.query(Product).all()
    return products


@app.get("/products/{product_id}", response_model=ProductOutput)
def get_product(product_id: int, session: Session = Depends(get_session)):
    product = session.query(Product).filter(Product._id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.put("/products/{product_id}", response_model=ProductOutput)
def update_product(product_id: int, product: ProductInput = Depends(ProductInput.as_form),
                   session: Session = Depends(get_session)):
    db_product = session.query(Product).filter(Product._id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    db_product.name = product.name
    db_product.description = product.description
    db_product.price = product.price
    db_product.quantity = product.quantity
    session.commit()
    session.refresh(db_product)
    return db_product


@app.delete("/products/{product_id}")
def delete_product(product_id: int, session: Session = Depends(get_session)):
    db_product = session.query(Product).filter(Product._id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    session.delete(db_product)
    session.commit()
    return {"message": "Product deleted successfully"}
