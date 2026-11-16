@echo off
rem Promotoria (estoque.maisvida.cloud): manda o faturamento e os brindes do ERP para o app.
rem Dois cliques: le a copia do banco do ERP, envia as notas de venda e de brinde dos ultimos 120 dias e mostra o
rem resumo. O app troca as entradas de mercadoria do periodo pelas do envio.
rem Para so conferir a leitura, sem enviar nada: sincronizar-faturamento-e-brindes.bat --sem-enviar
cd /d "%~dp0"
python sincronizar.py %*
echo.
pause
