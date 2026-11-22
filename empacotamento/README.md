# Empacotamento do OrganizaLocal

Esta pasta contém os scripts e os recursos usados para gerar novas versões dos pacotes. Para instalar o programa, abra a [pasta Instaladores](../Instaladores/).

Execute o comando do pacote desejado na raiz do repositório.

| Pacote | Comando | Requisitos |
| --- | --- | --- |
| Windows `.exe` | `bash empacotamento/windows/build.sh` | NSIS (`makensis`) e `unzip`. O script baixa e confere o Python embutido. |
| Linux `.deb` | `bash empacotamento/linux/build-deb.sh` | `dpkg-deb`. |

Os arquivos gerados ficam em `dist/`.
