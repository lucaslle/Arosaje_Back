# app/security.py
import hashlib
import hmac
import base64
from cryptography.fernet import Fernet
from app.config import settings

class SecurityManager:
    def __init__(self):
        # Assurer que la clé est au format correct pour Fernet
        self.fernet = Fernet(self._prepare_key(settings.ENCRYPTION_KEY))
        self.hash_key = settings.ENCRYPTION_KEY.encode()
    
    def _prepare_key(self, key_string):
        """Convertit une chaîne quelconque en une clé Fernet valide de 32 bytes en base64"""
        if len(key_string) == 44 and key_string[-2:] == '==':
            # C'est probablement déjà une clé Fernet valide
            return key_string.encode()
        
        # Sinon, on crée une clé valide à partir de la chaîne fournie
        key_bytes = hashlib.sha256(key_string.encode()).digest()
        return base64.urlsafe_b64encode(key_bytes)
    
    def hash_value(self, value):
        """HMAC-SHA-256 d'une valeur pour l'indexation : sans la clé, impossible de retrouver un téléphone par force brute"""
        if value is None:
            return None
        return hmac.new(self.hash_key, value.encode(), hashlib.sha256).hexdigest()
    
    def encrypt_value(self, value):
        """Chiffre une valeur pour le stockage sécurisé"""
        if value is None:
            return None
        return self.fernet.encrypt(value.encode()).decode()
    
    def decrypt_value(self, encrypted_value):
        """Déchiffre une valeur chiffrée"""
        if encrypted_value is None:
            return None
        return self.fernet.decrypt(encrypted_value.encode()).decode()

security_manager = SecurityManager()
