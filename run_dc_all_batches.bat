@echo off
title Dhaka College - Scraping ALL Batches
chcp 65001 >nul
echo ======================================================
echo   Dhaka College (DC) Scraping ALL Batches
echo ======================================================
echo.
python "scraper_dc.py" --batch all
echo.
echo Process finished.
pause
