import firebase_admin
from firebase_admin import credentials, firestore, storage
import os

# Inicializar Firebase apenas uma vez
try:
    # Tenta pegar app já inicializado
    firebase_admin.get_app()
    print("✅ Firebase já estava inicializado")
except ValueError:
    # App não existe, então inicializa
    cred_path = os.getenv(
        "FIREBASE_KEY_PATH",
        "config/firebase-key.json"
    )
    
    print(f"🔧 Inicializando Firebase com: {cred_path}")
    
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'seu-projeto.appspot.com'  # Substitua isso!
    })
    print("✅ Firebase inicializado com sucesso!")

# Inicializar Firestore
db = firestore.client()