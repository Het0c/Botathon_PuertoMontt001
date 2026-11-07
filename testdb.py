
from database import supabase

def obtener_roles():
    respuesta = (
        supabase.table("roles")
        .select("*")
        .execute()
    )
    return respuesta.data

roles = obtener_roles()

for rol in roles:
    print(rol)
