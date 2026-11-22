#!/usr/bin/env python3
"""ECR sin la AWS CLI: crea los repositorios si faltan y hace `docker login` (el token no se imprime).
Uso: ecr.py crear-y-login | borrar"""
import base64, subprocess, sys, boto3
REG = "us-east-1"; REPOS = ["taq-plataforma", "taq-jmeter", "taq-panel"]
ecr = boto3.client("ecr", region_name=REG)
if sys.argv[1] == "crear-y-login":
    for r in REPOS:
        try: ecr.create_repository(repositoryName=r, tags=[{"Key": "proyecto", "Value": "taq-reto4"}]); print("repositorio creado:", r)
        except ecr.exceptions.RepositoryAlreadyExistsException: print("repositorio existe:", r)
    a = ecr.get_authorization_token()["authorizationData"][0]
    user, pwd = base64.b64decode(a["authorizationToken"]).decode().split(":", 1)
    subprocess.run(["docker", "login", "--username", user, "--password-stdin", a["proxyEndpoint"]], input=pwd.encode(), check=True)
elif sys.argv[1] == "borrar":
    for r in REPOS:
        try: ecr.delete_repository(repositoryName=r, force=True); print("repositorio borrado:", r)
        except ecr.exceptions.RepositoryNotFoundException: pass
