#!/usr/bin/env python3
"""
Slum News Mapper - REFINED VERSION
- GDELT API only
- Dynamic legend intervals
- Refined filtering and visualization
- Improved circle scaling and transparency
"""

import requests
import re
import json
import pandas as pd
from datetime import datetime, timedelta
import time
from collections import defaultdict, Counter
import hashlib
import math

class RefinedSlumMapper:
    def __init__(self):
        # COMPREHENSIVE GLOBAL SOUTH DATABASE
        self.location_db = self.load_extended_database()
        
        # MULTILINGUAL SLUM KEYWORDS
        self.slum_keywords = self.load_multilingual_keywords()
        
        # Cache for processed locations
        self.location_cache = {}
        
    def load_extended_database(self):
        """Load comprehensive database of slums, cities, and countries across Global South"""
        location_db = {
            # AFRICA - EXPANDED
            
            # Nigeria (expanded)
            'makoko': {'lat': 6.5244, 'lon': 3.3792, 'type': 'slum', 'city': 'Lagos', 'country': 'Nigeria'},
            'ajegunle': {'lat': 6.5244, 'lon': 3.3792, 'type': 'slum', 'city': 'Lagos', 'country': 'Nigeria'},
            'badia': {'lat': 6.5244, 'lon': 3.3792, 'type': 'slum', 'city': 'Lagos', 'country': 'Nigeria'},
            'ilaje': {'lat': 6.5244, 'lon': 3.3792, 'type': 'slum', 'city': 'Lagos', 'country': 'Nigeria'},
            'iwaya': {'lat': 6.5244, 'lon': 3.3792, 'type': 'slum', 'city': 'Lagos', 'country': 'Nigeria'},
            'maroko': {'lat': 6.5244, 'lon': 3.3792, 'type': 'slum', 'city': 'Lagos', 'country': 'Nigeria'},
            'mushin': {'lat': 6.5244, 'lon': 3.3792, 'type': 'slum', 'city': 'Lagos', 'country': 'Nigeria'},
            'ojuelegba': {'lat': 6.5244, 'lon': 3.3792, 'type': 'slum', 'city': 'Lagos', 'country': 'Nigeria'},
            'bariga': {'lat': 6.5244, 'lon': 3.3792, 'type': 'slum', 'city': 'Lagos', 'country': 'Nigeria'},
            'agege': {'lat': 6.5244, 'lon': 3.3792, 'type': 'slum', 'city': 'Lagos', 'country': 'Nigeria'},
            
            # Kenya (expanded)
            'kibera': {'lat': -1.2921, 'lon': 36.8219, 'type': 'slum', 'city': 'Nairobi', 'country': 'Kenya'},
            'mathare': {'lat': -1.2709, 'lon': 36.8540, 'type': 'slum', 'city': 'Nairobi', 'country': 'Kenya'},
            'kawangware': {'lat': -1.2864, 'lon': 36.8172, 'type': 'slum', 'city': 'Nairobi', 'country': 'Kenya'},
            'korogocho': {'lat': -1.2450, 'lon': 36.8967, 'type': 'slum', 'city': 'Nairobi', 'country': 'Kenya'},
            'dandora': {'lat': -1.2450, 'lon': 36.8967, 'type': 'slum', 'city': 'Nairobi', 'country': 'Kenya'},
            'mukuru': {'lat': -1.2921, 'lon': 36.8219, 'type': 'slum', 'city': 'Nairobi', 'country': 'Kenya'},
            'kariobangi': {'lat': -1.2709, 'lon': 36.8540, 'type': 'slum', 'city': 'Nairobi', 'country': 'Kenya'},
            'huruma': {'lat': -1.2709, 'lon': 36.8540, 'type': 'slum', 'city': 'Nairobi', 'country': 'Kenya'},
            
            # South Africa (expanded)
            'soweto': {'lat': -26.2485, 'lon': 27.8540, 'type': 'slum', 'city': 'Johannesburg', 'country': 'South Africa'},
            'khayelitsha': {'lat': -33.9720, 'lon': 18.6385, 'type': 'slum', 'city': 'Cape Town', 'country': 'South Africa'},
            'alexandra': {'lat': -26.1065, 'lon': 28.1123, 'type': 'slum', 'city': 'Johannesburg', 'country': 'South Africa'},
            'gugulethu': {'lat': -33.9720, 'lon': 18.6385, 'type': 'slum', 'city': 'Cape Town', 'country': 'South Africa'},
            'diepsloot': {'lat': -25.9398, 'lon': 27.9689, 'type': 'slum', 'city': 'Johannesburg', 'country': 'South Africa'},
            'langa': {'lat': -33.9441, 'lon': 18.5281, 'type': 'slum', 'city': 'Cape Town', 'country': 'South Africa'},
            'mitchells plain': {'lat': -34.0444, 'lon': 18.6194, 'type': 'slum', 'city': 'Cape Town', 'country': 'South Africa'},
            'phola park': {'lat': -26.2041, 'lon': 28.0473, 'type': 'slum', 'city': 'Johannesburg', 'country': 'South Africa'},
            
            # Ghana (expanded)
            'old fadama': {'lat': 5.5500, 'lon': -0.2167, 'type': 'slum', 'city': 'Accra', 'country': 'Ghana'},
            'agbogbloshie': {'lat': 5.5500, 'lon': -0.2167, 'type': 'slum', 'city': 'Accra', 'country': 'Ghana'},
            'jamestown': {'lat': 5.5500, 'lon': -0.2167, 'type': 'slum', 'city': 'Accra', 'country': 'Ghana'},
            
            # Tanzania (expanded)
            'tandale': {'lat': -6.8000, 'lon': 39.2833, 'type': 'slum', 'city': 'Dar es Salaam', 'country': 'Tanzania'},
            'manzese': {'lat': -6.8000, 'lon': 39.2833, 'type': 'slum', 'city': 'Dar es Salaam', 'country': 'Tanzania'},
            'kigamboni': {'lat': -6.8000, 'lon': 39.2833, 'type': 'slum', 'city': 'Dar es Salaam', 'country': 'Tanzania'},
            
            # Ethiopia (expanded)
            'kechene': {'lat': 9.0000, 'lon': 38.7500, 'type': 'slum', 'city': 'Addis Ababa', 'country': 'Ethiopia'},
            'yeka': {'lat': 9.0000, 'lon': 38.7500, 'type': 'slum', 'city': 'Addis Ababa', 'country': 'Ethiopia'},
            'merkato': {'lat': 9.0320, 'lon': 38.7469, 'type': 'slum', 'city': 'Addis Ababa', 'country': 'Ethiopia'},
            
            # DRC (expanded)
            'masina': {'lat': -4.4419, 'lon': 15.2663, 'type': 'slum', 'city': 'Kinshasa', 'country': 'DRC'},
            'ndjili': {'lat': -4.4419, 'lon': 15.2663, 'type': 'slum', 'city': 'Kinshasa', 'country': 'DRC'},
            'matonge': {'lat': -4.4419, 'lon': 15.2663, 'type': 'slum', 'city': 'Kinshasa', 'country': 'DRC'},
            
            # Senegal
            'medina': {'lat': 14.7167, 'lon': -17.4677, 'type': 'slum', 'city': 'Dakar', 'country': 'Senegal'},
            'guediawaye': {'lat': 14.7167, 'lon': -17.4677, 'type': 'slum', 'city': 'Dakar', 'country': 'Senegal'},
            
            # Ivory Coast
            'abobo': {'lat': 5.3599, 'lon': -4.0083, 'type': 'slum', 'city': 'Abidjan', 'country': 'Ivory Coast'},
            
            # Zambia
            'kalingalinga': {'lat': -15.3875, 'lon': 28.3228, 'type': 'slum', 'city': 'Lusaka', 'country': 'Zambia'},
            'chawama': {'lat': -15.3875, 'lon': 28.3228, 'type': 'slum', 'city': 'Lusaka', 'country': 'Zambia'},
            
            # Zimbabwe
            'epworth': {'lat': -17.8252, 'lon': 31.0335, 'type': 'slum', 'city': 'Harare', 'country': 'Zimbabwe'},
            'mbare': {'lat': -17.8252, 'lon': 31.0335, 'type': 'slum', 'city': 'Harare', 'country': 'Zimbabwe'},
            
            # Mozambique
            'maxaquene': {'lat': -25.9653, 'lon': 32.5892, 'type': 'slum', 'city': 'Maputo', 'country': 'Mozambique'},
            
            # Madagascar
            'andavamamba': {'lat': -18.8792, 'lon': 47.5079, 'type': 'slum', 'city': 'Antananarivo', 'country': 'Madagascar'},
            
            # ASIA - EXPANDED
            
            # India (expanded)
            'dharavi': {'lat': 19.0450, 'lon': 72.8560, 'type': 'slum', 'city': 'Mumbai', 'country': 'India'},
            'jhuggi': {'lat': 28.7041, 'lon': 77.1025, 'type': 'slum', 'city': 'Delhi', 'country': 'India'},
            'basti': {'lat': 28.7041, 'lon': 77.1025, 'type': 'slum', 'city': 'Delhi', 'country': 'India'},
            'basant nagar': {'lat': 13.0827, 'lon': 80.2707, 'type': 'slum', 'city': 'Chennai', 'country': 'India'},
            'annawadi': {'lat': 19.0760, 'lon': 72.8777, 'type': 'slum', 'city': 'Mumbai', 'country': 'India'},
            'govindpuri': {'lat': 28.5400, 'lon': 77.2600, 'type': 'slum', 'city': 'Delhi', 'country': 'India'},
            'sanjay colony': {'lat': 28.5400, 'lon': 77.2600, 'type': 'slum', 'city': 'Delhi', 'country': 'India'},
            'jhilmil': {'lat': 28.7041, 'lon': 77.1025, 'type': 'slum', 'city': 'Delhi', 'country': 'India'},
            'katputli colony': {'lat': 28.7041, 'lon': 77.1025, 'type': 'slum', 'city': 'Delhi', 'country': 'India'},
            'sangam vihar': {'lat': 28.7041, 'lon': 77.1025, 'type': 'slum', 'city': 'Delhi', 'country': 'India'},
            'rampuri': {'lat': 28.7041, 'lon': 77.1025, 'type': 'slum', 'city': 'Delhi', 'country': 'India'},
            
            # Bangladesh (expanded)
            'korail': {'lat': 23.8103, 'lon': 90.4125, 'type': 'slum', 'city': 'Dhaka', 'country': 'Bangladesh'},
            'mohammadpur': {'lat': 23.8103, 'lon': 90.4125, 'type': 'slum', 'city': 'Dhaka', 'country': 'Bangladesh'},
            'bhashantek': {'lat': 23.8103, 'lon': 90.4125, 'type': 'slum', 'city': 'Dhaka', 'country': 'Bangladesh'},
            'uttara': {'lat': 23.8103, 'lon': 90.4125, 'type': 'slum', 'city': 'Dhaka', 'country': 'Bangladesh'},
            'mirpur': {'lat': 23.8103, 'lon': 90.4125, 'type': 'slum', 'city': 'Dhaka', 'country': 'Bangladesh'},
            
            # Pakistan (expanded)
            'orangi town': {'lat': 24.8607, 'lon': 67.0011, 'type': 'slum', 'city': 'Karachi', 'country': 'Pakistan'},
            'lyari': {'lat': 24.8607, 'lon': 67.0011, 'type': 'slum', 'city': 'Karachi', 'country': 'Pakistan'},
            'katchi abadi': {'lat': 31.5497, 'lon': 74.3436, 'type': 'slum', 'city': 'Lahore', 'country': 'Pakistan'},
            'sadar': {'lat': 24.8607, 'lon': 67.0011, 'type': 'slum', 'city': 'Karachi', 'country': 'Pakistan'},
            'gulshan-e-hadeed': {'lat': 24.8607, 'lon': 67.0011, 'type': 'slum', 'city': 'Karachi', 'country': 'Pakistan'},
            
            # Philippines (expanded)
            'tondo': {'lat': 14.5995, 'lon': 120.9842, 'type': 'slum', 'city': 'Manila', 'country': 'Philippines'},
            'bagong silangan': {'lat': 14.5995, 'lon': 120.9842, 'type': 'slum', 'city': 'Manila', 'country': 'Philippines'},
            'payatas': {'lat': 14.5995, 'lon': 120.9842, 'type': 'slum', 'city': 'Manila', 'country': 'Philippines'},
            'smokey mountain': {'lat': 14.5995, 'lon': 120.9842, 'type': 'slum', 'city': 'Manila', 'country': 'Philippines'},
            'baseco': {'lat': 14.5995, 'lon': 120.9842, 'type': 'slum', 'city': 'Manila', 'country': 'Philippines'},
            
            # Indonesia (expanded)
            'kampung melayu': {'lat': -6.2088, 'lon': 106.8456, 'type': 'slum', 'city': 'Jakarta', 'country': 'Indonesia'},
            'kampung bunga': {'lat': -6.2088, 'lon': 106.8456, 'type': 'slum', 'city': 'Jakarta', 'country': 'Indonesia'},
            'rw 05': {'lat': -6.2088, 'lon': 106.8456, 'type': 'slum', 'city': 'Jakarta', 'country': 'Indonesia'},
            'kampung pulo': {'lat': -6.2088, 'lon': 106.8456, 'type': 'slum', 'city': 'Jakarta', 'country': 'Indonesia'},
            'kampung kali': {'lat': -6.2088, 'lon': 106.8456, 'type': 'slum', 'city': 'Jakarta', 'country': 'Indonesia'},
            
            # Thailand
            'khlong toei': {'lat': 13.7563, 'lon': 100.5018, 'type': 'slum', 'city': 'Bangkok', 'country': 'Thailand'},
            
            # Vietnam
            'kim lien': {'lat': 21.0285, 'lon': 105.8542, 'type': 'slum', 'city': 'Hanoi', 'country': 'Vietnam'},
            
            # LATIN AMERICA - EXPANDED
            
            # Brazil (expanded)
            'rocinha': {'lat': -22.9885, 'lon': -43.2476, 'type': 'slum', 'city': 'Rio de Janeiro', 'country': 'Brazil'},
            'complexo do alemão': {'lat': -22.8526, 'lon': -43.2702, 'type': 'slum', 'city': 'Rio de Janeiro', 'country': 'Brazil'},
            'cidade de deus': {'lat': -22.9487, 'lon': -43.3670, 'type': 'slum', 'city': 'Rio de Janeiro', 'country': 'Brazil'},
            'paraisopolis': {'lat': -23.6148, 'lon': -46.7196, 'type': 'slum', 'city': 'São Paulo', 'country': 'Brazil'},
            'heliopolis': {'lat': -23.6148, 'lon': -46.7196, 'type': 'slum', 'city': 'São Paulo', 'country': 'Brazil'},
            'favela da maré': {'lat': -22.9068, 'lon': -43.1729, 'type': 'slum', 'city': 'Rio de Janeiro', 'country': 'Brazil'},
            'vidigal': {'lat': -22.9885, 'lon': -43.2476, 'type': 'slum', 'city': 'Rio de Janeiro', 'country': 'Brazil'},
            'cantagalo': {'lat': -22.9885, 'lon': -43.2476, 'type': 'slum', 'city': 'Rio de Janeiro', 'country': 'Brazil'},
            'manguinhos': {'lat': -22.9885, 'lon': -43.2476, 'type': 'slum', 'city': 'Rio de Janeiro', 'country': 'Brazil'},
            
            # Mexico (expanded)
            'ciudad nezahualcóyotl': {'lat': 19.4000, 'lon': -99.0500, 'type': 'slum', 'city': 'Mexico City', 'country': 'Mexico'},
            'ecatepec': {'lat': 19.6000, 'lon': -99.0500, 'type': 'slum', 'city': 'Mexico City', 'country': 'Mexico'},
            'iztapalapa': {'lat': 19.4326, 'lon': -99.1332, 'type': 'slum', 'city': 'Mexico City', 'country': 'Mexico'},
            'tlahuac': {'lat': 19.4326, 'lon': -99.1332, 'type': 'slum', 'city': 'Mexico City', 'country': 'Mexico'},
            
            # Colombia (expanded)
            'ciudad bolívar': {'lat': 4.5709, 'lon': -74.2973, 'type': 'slum', 'city': 'Bogotá', 'country': 'Colombia'},
            'soacha': {'lat': 4.5709, 'lon': -74.2973, 'type': 'slum', 'city': 'Bogotá', 'country': 'Colombia'},
            'bello': {'lat': 6.2442, 'lon': -75.5736, 'type': 'slum', 'city': 'Medellín', 'country': 'Colombia'},
            'comuna 13': {'lat': 6.2442, 'lon': -75.5736, 'type': 'slum', 'city': 'Medellín', 'country': 'Colombia'},
            
            # Argentina (expanded)
            'villa 31': {'lat': -34.6037, 'lon': -58.3816, 'type': 'slum', 'city': 'Buenos Aires', 'country': 'Argentina'},
            'villa miseria': {'lat': -34.6037, 'lon': -58.3816, 'type': 'slum', 'city': 'Buenos Aires', 'country': 'Argentina'},
            'villa 1-11-14': {'lat': -34.6037, 'lon': -58.3816, 'type': 'slum', 'city': 'Buenos Aires', 'country': 'Argentina'},
            'villa lugano': {'lat': -34.6037, 'lon': -58.3816, 'type': 'slum', 'city': 'Buenos Aires', 'country': 'Argentina'},
            
            # Peru (expanded)
            'pamplona alta': {'lat': -12.0464, 'lon': -77.0428, 'type': 'slum', 'city': 'Lima', 'country': 'Peru'},
            'san juan de lurigancho': {'lat': -12.0464, 'lon': -77.0428, 'type': 'slum', 'city': 'Lima', 'country': 'Peru'},
            'villa el salvador': {'lat': -12.0464, 'lon': -77.0428, 'type': 'slum', 'city': 'Lima', 'country': 'Peru'},
            'comas': {'lat': -12.0464, 'lon': -77.0428, 'type': 'slum', 'city': 'Lima', 'country': 'Peru'},
            
            # Venezuela
            'petare': {'lat': 10.4806, 'lon': -66.9036, 'type': 'slum', 'city': 'Caracas', 'country': 'Venezuela'},
            'barrio 23 de enero': {'lat': 10.4806, 'lon': -66.9036, 'type': 'slum', 'city': 'Caracas', 'country': 'Venezuela'},
            
            # Chile
            'la legua': {'lat': -33.4489, 'lon': -70.6693, 'type': 'slum', 'city': 'Santiago', 'country': 'Chile'},
            'población la victoria': {'lat': -33.4489, 'lon': -70.6693, 'type': 'slum', 'city': 'Santiago', 'country': 'Chile'},
            
            # Ecuador
            'ciudadela iess': {'lat': -0.1807, 'lon': -78.4678, 'type': 'slum', 'city': 'Quito', 'country': 'Ecuador'},
            
            # Bolivia
            'el alto': {'lat': -16.5000, 'lon': -68.1500, 'type': 'slum', 'city': 'La Paz', 'country': 'Bolivia'},
            
            # MAJOR GLOBAL SOUTH CITIES (for fallback) - EXPANDED
            'lagos': {'lat': 6.5244, 'lon': 3.3792, 'type': 'city', 'city': 'Lagos', 'country': 'Nigeria'},
            'nairobi': {'lat': -1.2864, 'lon': 36.8172, 'type': 'city', 'city': 'Nairobi', 'country': 'Kenya'},
            'cairo': {'lat': 30.0444, 'lon': 31.2357, 'type': 'city', 'city': 'Cairo', 'country': 'Egypt'},
            'johannesburg': {'lat': -26.2041, 'lon': 28.0473, 'type': 'city', 'city': 'Johannesburg', 'country': 'South Africa'},
            'cape town': {'lat': -33.9249, 'lon': 18.4241, 'type': 'city', 'city': 'Cape Town', 'country': 'South Africa'},
            'accra': {'lat': 5.6037, 'lon': -0.1870, 'type': 'city', 'city': 'Accra', 'country': 'Ghana'},
            'dar es salaam': {'lat': -6.7924, 'lon': 39.2083, 'type': 'city', 'city': 'Dar es Salaam', 'country': 'Tanzania'},
            'kampala': {'lat': 0.3476, 'lon': 32.5825, 'type': 'city', 'city': 'kampala', 'country': 'Uganda'},
            'addis ababa': {'lat': 9.0320, 'lon': 38.7469, 'type': 'city', 'city': 'Addis Ababa', 'country': 'Ethiopia'},
            'kinshasa': {'lat': -4.4419, 'lon': 15.2663, 'type': 'city', 'city': 'Kinshasa', 'country': 'DRC'},
            'abidjan': {'lat': 5.3599, 'lon': -4.0083, 'type': 'city', 'city': 'Abidjan', 'country': 'Ivory Coast'},
            'dakar': {'lat': 14.7167, 'lon': -17.4677, 'type': 'city', 'city': 'Dakar', 'country': 'Senegal'},
            'algiers': {'lat': 36.7538, 'lon': 3.0588, 'type': 'city', 'city': 'Algiers', 'country': 'Algeria'},
            'casablanca': {'lat': 33.5731, 'lon': -7.5898, 'type': 'city', 'city': 'Casablanca', 'country': 'Morocco'},
            'rabat': {'lat': 34.0209, 'lon': -6.8416, 'type': 'city', 'city': 'Rabat', 'country': 'Morocco'},
            'tunis': {'lat': 36.8065, 'lon': 10.1815, 'type': 'city', 'city': 'Tunis', 'country': 'Tunisia'},
            'harare': {'lat': -17.8252, 'lon': 31.0335, 'type': 'city', 'city': 'Harare', 'country': 'Zimbabwe'},
            'lusaka': {'lat': -15.3875, 'lon': 28.3228, 'type': 'city', 'city': 'Lusaka', 'country': 'Zambia'},
            'maputo': {'lat': -25.9653, 'lon': 32.5892, 'type': 'city', 'city': 'Maputo', 'country': 'Mozambique'},
            'antananarivo': {'lat': -18.8792, 'lon': 47.5079, 'type': 'city', 'city': 'Antananarivo', 'country': 'Madagascar'},
            'yaoundé': {'lat': 3.8480, 'lon': 11.5021, 'type': 'city', 'city': 'Yaoundé', 'country': 'Cameroon'},
            'douala': {'lat': 4.0511, 'lon': 9.7679, 'type': 'city', 'city': 'Douala', 'country': 'Cameroon'},
            'luanda': {'lat': -8.8390, 'lon': 13.2894, 'type': 'city', 'city': 'Luanda', 'country': 'Angola'},
            'mumbai': {'lat': 19.0760, 'lon': 72.8777, 'type': 'city', 'city': 'Mumbai', 'country': 'India'},
            'delhi': {'lat': 28.7041, 'lon': 77.1025, 'type': 'city', 'city': 'Delhi', 'country': 'India'},
            'kolkata': {'lat': 22.5726, 'lon': 88.3639, 'type': 'city', 'city': 'Kolkata', 'country': 'India'},
            'chennai': {'lat': 13.0827, 'lon': 80.2707, 'type': 'city', 'city': 'Chennai', 'country': 'India'},
            'bangalore': {'lat': 12.9716, 'lon': 77.5946, 'type': 'city', 'city': 'Bangalore', 'country': 'India'},
            'hyderabad': {'lat': 17.3850, 'lon': 78.4867, 'type': 'city', 'city': 'Hyderabad', 'country': 'India'},
            'ahmedabad': {'lat': 23.0225, 'lon': 72.5714, 'type': 'city', 'city': 'Ahmedabad', 'country': 'India'},
            'pune': {'lat': 18.5204, 'lon': 73.8567, 'type': 'city', 'city': 'Pune', 'country': 'India'},
            'surat': {'lat': 21.1702, 'lon': 72.8311, 'type': 'city', 'city': 'Surat', 'country': 'India'},
            'jaipur': {'lat': 26.9124, 'lon': 75.7873, 'type': 'city', 'city': 'Jaipur', 'country': 'India'},
            'karachi': {'lat': 24.8607, 'lon': 67.0011, 'type': 'city', 'city': 'Karachi', 'country': 'Pakistan'},
            'lahore': {'lat': 31.5497, 'lon': 74.3436, 'type': 'city', 'city': 'Lahore', 'country': 'Pakistan'},
            'islamabad': {'lat': 33.6844, 'lon': 73.0479, 'type': 'city', 'city': 'Islamabad', 'country': 'Pakistan'},
            'dhaka': {'lat': 23.8103, 'lon': 90.4125, 'type': 'city', 'city': 'Dhaka', 'country': 'Bangladesh'},
            'chittagong': {'lat': 22.3569, 'lon': 91.7832, 'type': 'city', 'city': 'Chittagong', 'country': 'Bangladesh'},
            'jakarta': {'lat': -6.2088, 'lon': 106.8456, 'type': 'city', 'city': 'Jakarta', 'country': 'Indonesia'},
            'surabaya': {'lat': -7.2575, 'lon': 112.7521, 'type': 'city', 'city': 'Surabaya', 'country': 'Indonesia'},
            'bandung': {'lat': -6.9175, 'lon': 107.6191, 'type': 'city', 'city': 'Bandung', 'country': 'Indonesia'},
            'manila': {'lat': 14.5995, 'lon': 120.9842, 'type': 'city', 'city': 'Manila', 'country': 'Philippines'},
            'quezon city': {'lat': 14.6760, 'lon': 121.0437, 'type': 'city', 'city': 'Quezon City', 'country': 'Philippines'},
            'bangkok': {'lat': 13.7563, 'lon': 100.5018, 'type': 'city', 'city': 'Bangkok', 'country': 'Thailand'},
            'ho chi minh city': {'lat': 10.8231, 'lon': 106.6297, 'type': 'city', 'city': 'Ho Chi Minh City', 'country': 'Vietnam'},
            'hanoi': {'lat': 21.0285, 'lon': 105.8542, 'type': 'city', 'city': 'Hanoi', 'country': 'Vietnam'},
            'riyadh': {'lat': 24.7136, 'lon': 46.6753, 'type': 'city', 'city': 'Riyadh', 'country': 'Saudi Arabia'},
            'jeddah': {'lat': 21.4858, 'lon': 39.1925, 'type': 'city', 'city': 'Jeddah', 'country': 'Saudi Arabia'},
            'rio de janeiro': {'lat': -22.9068, 'lon': -43.1729, 'type': 'city', 'city': 'Rio de Janeiro', 'country': 'Brazil'},
            'são paulo': {'lat': -23.5505, 'lon': -46.6333, 'type': 'city', 'city': 'São Paulo', 'country': 'Brazil'},
            'brasília': {'lat': -15.8267, 'lon': -47.9218, 'type': 'city', 'city': 'Brasília', 'country': 'Brazil'},
            'salvador': {'lat': -12.9714, 'lon': -38.5014, 'type': 'city', 'city': 'Salvador', 'country': 'Brazil'},
            'fortaleza': {'lat': -3.7319, 'lon': -38.5267, 'type': 'city', 'city': 'Fortaleza', 'country': 'Brazil'},
            'belo horizonte': {'lat': -19.9167, 'lon': -43.9345, 'type': 'city', 'city': 'Belo Horizonte', 'country': 'Brazil'},
            'mexico city': {'lat': 19.4326, 'lon': -99.1332, 'type': 'city', 'city': 'Mexico City', 'country': 'Mexico'},
            'guadalajara': {'lat': 20.6597, 'lon': -103.3496, 'type': 'city', 'city': 'Guadalajara', 'country': 'Mexico'},
            'monterrey': {'lat': 25.6866, 'lon': -100.3161, 'type': 'city', 'city': 'Monterrey', 'country': 'Mexico'},
            'bogotá': {'lat': 4.7110, 'lon': -74.0721, 'type': 'city', 'city': 'Bogotá', 'country': 'Colombia'},
            'medellín': {'lat': 6.2442, 'lon': -75.5736, 'type': 'city', 'city': 'Medellín', 'country': 'Colombia'},
            'cali': {'lat': 3.4516, 'lon': -76.5320, 'type': 'city', 'city': 'Cali', 'country': 'Colombia'},
            'lima': {'lat': -12.0464, 'lon': -77.0428, 'type': 'city', 'city': 'Lima', 'country': 'Peru'},
            'buenos aires': {'lat': -34.6037, 'lon': -58.3816, 'type': 'city', 'city': 'Buenos Aires', 'country': 'Argentina'},
            'córdoba': {'lat': -31.4201, 'lon': -64.1888, 'type': 'city', 'city': 'Córdoba', 'country': 'Argentina'},
            'rosario': {'lat': -32.9587, 'lon': -60.6930, 'type': 'city', 'city': 'Rosario', 'country': 'Argentina'},
            'santiago': {'lat': -33.4489, 'lon': -70.6693, 'type': 'city', 'city': 'Santiago', 'country': 'Chile'},
            'caracas': {'lat': 10.4806, 'lon': -66.9036, 'type': 'city', 'city': 'Caracas', 'country': 'Venezuela'},
            'quito': {'lat': -0.1807, 'lon': -78.4678, 'type': 'city', 'city': 'Quito', 'country': 'Ecuador'},
            'guayaquil': {'lat': -2.1700, 'lon': -79.9224, 'type': 'city', 'city': 'Guayaquil', 'country': 'Ecuador'},
            'la paz': {'lat': -16.5000, 'lon': -68.1500, 'type': 'city', 'city': 'La Paz', 'country': 'Bolivia'},
            'santa cruz': {'lat': -17.7833, 'lon': -63.1833, 'type': 'city', 'city': 'Santa Cruz', 'country': 'Bolivia'},
            'montevideo': {'lat': -34.9011, 'lon': -56.1645, 'type': 'city', 'city': 'Montevideo', 'country': 'Uruguay'},
            'asuncion': {'lat': -25.2637, 'lon': -57.5759, 'type': 'city', 'city': 'Asunción', 'country': 'Paraguay'},
            'havana': {'lat': 23.1136, 'lon': -82.3666, 'type': 'city', 'city': 'Havana', 'country': 'Cuba'},
            
            # COUNTRIES (final fallback) - EXPANDED
            'nigeria': {'lat': 9.0820, 'lon': 8.6753, 'type': 'country', 'city': 'Abuja', 'country': 'Nigeria'},
            'kenya': {'lat': -0.0236, 'lon': 37.9062, 'type': 'country', 'city': 'Nairobi', 'country': 'Kenya'},
            'south africa': {'lat': -30.5595, 'lon': 22.9375, 'type': 'country', 'city': 'Pretoria', 'country': 'South Africa'},
            'india': {'lat': 20.5937, 'lon': 78.9629, 'type': 'country', 'city': 'New Delhi', 'country': 'India'},
            'brazil': {'lat': -14.2350, 'lon': -51.9253, 'type': 'country', 'city': 'Brasília', 'country': 'Brazil'},
            'bangladesh': {'lat': 23.6850, 'lon': 90.3563, 'type': 'country', 'city': 'Dhaka', 'country': 'Bangladesh'},
            'pakistan': {'lat': 30.3753, 'lon': 69.3451, 'type': 'country', 'city': 'Islamabad', 'country': 'Pakistan'},
            'philippines': {'lat': 12.8797, 'lon': 121.7740, 'type': 'country', 'city': 'Manila', 'country': 'Philippines'},
            'indonesia': {'lat': -0.7893, 'lon': 113.9213, 'type': 'country', 'city': 'Jakarta', 'country': 'Indonesia'},
            'mexico': {'lat': 23.6345, 'lon': -102.5528, 'type': 'country', 'city': 'Mexico City', 'country': 'Mexico'},
            'colombia': {'lat': 4.5709, 'lon': -74.2973, 'type': 'country', 'city': 'Bogotá', 'country': 'Colombia'},
            'argentina': {'lat': -38.4161, 'lon': -63.6167, 'type': 'country', 'city': 'Buenos Aires', 'country': 'Argentina'},
            'peru': {'lat': -9.1900, 'lon': -75.0152, 'type': 'country', 'city': 'Lima', 'country': 'Peru'},
            'ghana': {'lat': 7.9465, 'lon': -1.0232, 'type': 'country', 'city': 'Accra', 'country': 'Ghana'},
            'tanzania': {'lat': -6.3690, 'lon': 34.8888, 'type': 'country', 'city': 'Dodoma', 'country': 'Tanzania'},
            'ethiopia': {'lat': 9.1450, 'lon': 40.4897, 'type': 'country', 'city': 'Addis Ababa', 'country': 'Ethiopia'},
            'egypt': {'lat': 26.8206, 'lon': 30.8025, 'type': 'country', 'city': 'Cairo', 'country': 'Egypt'},
            'morocco': {'lat': 31.7917, 'lon': -7.0926, 'type': 'country', 'city': 'Rabat', 'country': 'Morocco'},
            'algeria': {'lat': 28.0339, 'lon': 1.6596, 'type': 'country', 'city': 'Algiers', 'country': 'Algeria'},
            'tunisia': {'lat': 33.8869, 'lon': 9.5375, 'type': 'country', 'city': 'Tunis', 'country': 'Tunisia'},
            'senegal': {'lat': 14.4974, 'lon': -14.4524, 'type': 'country', 'city': 'Dakar', 'country': 'Senegal'},
            'ivory coast': {'lat': 7.5400, 'lon': -5.5471, 'type': 'country', 'city': 'Yamoussoukro', 'country': 'Ivory Coast'},
            'cameroon': {'lat': 7.3697, 'lon': 12.3547, 'type': 'country', 'city': 'Yaoundé', 'country': 'Cameroon'},
            'angola': {'lat': -11.2027, 'lon': 17.8739, 'type': 'country', 'city': 'Luanda', 'country': 'Angola'},
            'zimbabwe': {'lat': -19.0154, 'lon': 29.1549, 'type': 'country', 'city': 'Harare', 'country': 'Zimbabwe'},
            'zambia': {'lat': -13.1339, 'lon': 27.8493, 'type': 'country', 'city': 'Lusaka', 'country': 'Zambia'},
            'mozambique': {'lat': -18.6657, 'lon': 35.5296, 'type': 'country', 'city': 'Maputo', 'country': 'Mozambique'},
            'madagascar': {'lat': -18.7669, 'lon': 46.8691, 'type': 'country', 'city': 'Antananarivo', 'country': 'Madagascar'},
            'thailand': {'lat': 15.8700, 'lon': 100.9925, 'type': 'country', 'city': 'Bangkok', 'country': 'Thailand'},
            'vietnam': {'lat': 14.0583, 'lon': 108.2772, 'type': 'country', 'city': 'Hanoi', 'country': 'Vietnam'},
            'malaysia': {'lat': 4.2105, 'lon': 101.9758, 'type': 'country', 'city': 'Kuala Lumpur', 'country': 'Malaysia'},
            'chile': {'lat': -35.6751, 'lon': -71.5430, 'type': 'country', 'city': 'Santiago', 'country': 'Chile'},
            'venezuela': {'lat': 6.4238, 'lon': -66.5897, 'type': 'country', 'city': 'Caracas', 'country': 'Venezuela'},
            'ecuador': {'lat': -1.8312, 'lon': -78.1834, 'type': 'country', 'city': 'Quito', 'country': 'Ecuador'},
            'bolivia': {'lat': -16.2902, 'lon': -63.5887, 'type': 'country', 'city': 'Sucre', 'country': 'Bolivia'},
            'paraguay': {'lat': -23.4425, 'lon': -58.4438, 'type': 'country', 'city': 'Asunción', 'country': 'Paraguay'},
            'uruguay': {'lat': -32.5228, 'lon': -55.7658, 'type': 'country', 'city': 'Montevideo', 'country': 'Uruguay'},
        }
        
        # Add common alternate spellings and variants
        additional_entries = {}
        for name, data in location_db.items():
            # Add capitalized version
            if name not in additional_entries:
                additional_entries[name.title()] = data
            
            # Add versions with accents/diacritics
            if 'são paulo' in name:
                additional_entries['sao paulo'] = data
            if 'bogotá' in name:
                additional_entries['bogota'] = data
            if 'ciudad bolívar' in name:
                additional_entries['ciudad bolivar'] = data
            if 'ciudad nezahualcóyotl' in name:
                additional_entries['ciudad nezahualcoyotl'] = data
            if 'favela da maré' in name:
                additional_entries['favela da mare'] = data
            if 'yaoundé' in name:
                additional_entries['yaounde'] = data
            if 'medellín' in name:
                additional_entries['medellin'] = data
            if 'asuncion' in name:
                additional_entries['asunción'] = data
        
        location_db.update(additional_entries)
        
        print(f"Loaded database with {len(location_db)} locations")
        return location_db
    
    def load_multilingual_keywords(self):
        """Load multilingual slum keywords"""
        return {
            'en': [
                'slum', 'slums', 'informal settlement', 'informal settlements',
                'shantytown', 'shantytowns', 'favela', 'favelas', 'township',
                'squatter', 'squatters', 'squatter settlement', 'ghetto', 'ghettos',
                'makeshift housing', 'urban poor', 'precarious housing',
                'jhuggi', 'basti', 'chawl', 'zopadpatti', 'gecekondu',
                'katchi abadi', 'unauthorized colony', 'illegal settlement',
                'urban slum', 'poverty area', 'deprived area', 'shack', 'shacks',
                'tenement', 'tenements', 'overcrowded housing'
            ],
            'pt': [
                'favela', 'favelas', 'comunidade', 'comunidades', 'invasão',
                'aglomerado', 'aglomerados', 'morrinho', 'assentamento informal',
                'habitação precária', 'cortiço', 'cortiços', 'periferia',
                'barraca', 'barracas', 'ocupação irregular', 'vilas', 'invasões'
            ],
            'es': [
                'barrio marginal', 'barrios marginales', 'asentamiento informal',
                'asentamientos informales', 'villa miseria', 'chabolismo',
                'tugurio', 'tugurios', 'barriada', 'barriadas', 'población callampa',
                'ciudad perdida', 'barrio pobre', 'villa de emergencia',
                'barrio bajo', 'barrios bajos', 'cinturón de miseria'
            ],
            'fr': [
                'bidonville', 'bidonvilles', 'taudis', 'quartier informel',
                'zone d\'habitation précaire', 'habitat précaire', 'quartier pauvre',
                'banlieue défavorisée', 'logement insalubre', 'quartier déshérité'
            ]
        }
    
    def get_all_search_queries(self):
        """Get all search queries: slum names + multilingual keywords"""
        queries = []
        
        # Add all slum names from database
        for location_name, location_data in self.location_db.items():
            if location_data.get('type') == 'slum':
                queries.append(location_name)
        
        # Add multilingual keywords
        for lang in ['en', 'pt', 'es', 'fr']:
            for keyword in self.slum_keywords[lang]:
                queries.append(keyword)
        
        # Remove duplicates
        unique_queries = list(set(queries))
        
        print(f"Total search queries: {len(unique_queries)}")
        print(f"  - Slum names: {len([q for q in unique_queries if q in [name for name, data in self.location_db.items() if data.get('type') == 'slum']])}")
        print(f"  - Keywords: {len(unique_queries) - len([q for q in unique_queries if q in [name for name, data in self.location_db.items() if data.get('type') == 'slum']])}")
        
        return unique_queries
    
    def search_gdelt_only(self):
        """Search GDELT with comprehensive queries"""
        articles = []
        
        print("🔍 Searching GDELT (recent news only)...\n")
        
        # Get all search queries
        queries = self.get_all_search_queries()
        
        print(f"Using ALL {len(queries)} search queries")
        
        for i, query in enumerate(queries):
            try:
                if i % 20 == 0:
                    print(f"   [{i+1}/{len(queries)}] Processing queries...")
                
                url = "https://api.gdeltproject.org/api/v2/doc/doc"
                params = {
                    'query': f'"{query}"',  # Exact phrase search
                    'mode': 'artlist',
                    'format': 'json',
                    'maxrecords': 50,
                    # REMOVE date restrictions to get more data
                    'sort': 'datedesc'
                }
                
                response = requests.get(url, params=params, timeout=20)
                
                if response.status_code == 200:
                    # Check if response has content
                    if not response.text or response.text.strip() == "":
                        # Skip empty responses
                        continue
                    
                    try:
                        data = response.json()
                    except json.JSONDecodeError:
                        # Skip JSON decode errors silently
                        continue
                    
                    if 'articles' in data:
                        for article in data['articles']:
                            seendate = article.get('seendate', '')
                            published_at = self.parse_gdelt_date(seendate)
                            
                            # Create article entry
                            articles.append({
                                'title': article.get('title', 'No title'),
                                'description': article.get('snippet', ''),
                                'content': article.get('snippet', '')[:500],
                                'url': article.get('url', ''),
                                'publishedAt': published_at,
                                'source': {'name': article.get('domain', 'Unknown')},
                                'language': article.get('language', 'en'),
                                'full_text': f"{article.get('title', '')} {article.get('snippet', '')}".lower(),
                                'search_query': query
                            })
                
                time.sleep(0.2)  # Reduced rate limiting for more queries
                
            except Exception as e:
                error_msg = str(e)
                if "JSON" in error_msg or "Expecting value" in error_msg:
                    # Skip JSON decode errors silently
                    continue
                else:
                    print(f"     Error for query '{query}': {str(e)[:50]}")
                    continue
        
        # Remove duplicates by URL
        seen_urls = set()
        unique_articles = []
        
        for article in articles:
            url = article.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_articles.append(article)
            elif not url:  # If no URL, use title hash
                title_hash = hashlib.md5(article['title'].encode()).hexdigest()
                if title_hash not in seen_urls:
                    seen_urls.add(title_hash)
                    unique_articles.append(article)
        
        print(f"\n📰 Found {len(unique_articles)} unique articles from GDELT")
        
        # Show top successful queries
        if unique_articles:
            query_counts = {}
            for article in unique_articles:
                query = article.get('search_query', 'unknown')
                query_counts[query] = query_counts.get(query, 0) + 1
            
            print("\n📊 Top 15 most successful queries:")
            for query, count in sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
                print(f"   '{query}': {count} articles")
        
        return unique_articles
    
    def parse_gdelt_date(self, seendate):
        """Parse GDELT date format to ISO 8601"""
        if not seendate or len(seendate) < 8:
            return datetime.now().isoformat() + "Z"
        
        try:
            # Format: YYYYMMDDHHMMSS
            year = int(seendate[:4])
            month = int(seendate[4:6])
            day = int(seendate[6:8])
            
            hour = 0
            minute = 0
            second = 0
            
            if len(seendate) >= 10:
                hour = int(seendate[8:10])
            if len(seendate) >= 12:
                minute = int(seendate[10:12])
            if len(seendate) >= 14:
                second = int(seendate[12:14])
            
            dt = datetime(year, month, day, hour, minute, second)
            return dt.isoformat() + "Z"
            
        except:
            return datetime.now().isoformat() + "Z"
    
    def extract_location_from_text(self, text):
        """Extract location from text using database only"""
        if not text:
            return None, None, None, None
        
        text_lower = text.lower()
        
        # Priority 1: Look for known slums (exact match)
        for location_name, location_data in self.location_db.items():
            if location_data.get('type') == 'slum':
                # Check for exact match or as a separate word
                pattern = r'\b' + re.escape(location_name.lower()) + r'\b'
                if re.search(pattern, text_lower):
                    return location_name, location_data['city'], location_data['country'], location_data
        
        # Priority 2: Look for cities
        for location_name, location_data in self.location_db.items():
            if location_data.get('type') == 'city':
                pattern = r'\b' + re.escape(location_name.lower()) + r'\b'
                if re.search(pattern, text_lower):
                    return None, location_name, location_data['country'], location_data
        
        # Priority 3: Look for countries
        for location_name, location_data in self.location_db.items():
            if location_data.get('type') == 'country':
                pattern = r'\b' + re.escape(location_name.lower()) + r'\b'
                if re.search(pattern, text_lower):
                    return None, location_data['city'], location_name, location_data
        
        return None, None, None, None
    
    def extract_event_type(self, text):
        """Extract event type from text"""
        if not text:
            return 'other'
        
        text_lower = text.lower()
        
        # Event keywords in multiple languages
        event_keywords = {
            'eviction': [
                'eviction', 'evictions', 'forced eviction', 'forced removal', 'expulsion',
                'despejo', 'despejos', 'remoção forçada', 'expulsão',  # Portuguese
                'desalojo', 'desalojos', 'desahucio',  # Spanish
                'expulsion', 'expulsions'  # French
            ],
            'demolition': [
                'demolition', 'demolitions', 'bulldoze', 'bulldozing', 'razed', 'torn down',
                'demolição', 'demolições',  # Portuguese
                'demolición', 'demoliciones',  # Spanish
                'démolition', 'démolitions'  # French
            ],
            'protest': [
                'protest', 'protests', 'demonstration', 'march', 'rally', 'strike',
                'protesto', 'protestos', 'manifestação', 'greve',  # Portuguese
                'protesta', 'protestas', 'manifestación', 'huelga',  # Spanish
                'protestation', 'manifestation', 'grève'  # French
            ],
            'fire': [
                'fire', 'blaze', 'arson', 'burning', 'incendiary', 'inferno',
                'incêndio', 'queimada',  # Portuguese
                'incendio', 'quema',  # Spanish
                'incendie', 'feu'  # French
            ],
            'flood': [
                'flood', 'flooding', 'inundation', 'deluge',
                'enchente', 'inundação',  # Portuguese
                'inundación',  # Spanish
                'inondation', 'déluge'  # French
            ],
            'land_rights': [
                'land rights', 'land conflict', 'land dispute', 'land grab', 'eviction',
                'direito à terra', 'conflito fundiário', 'disputa de terra',  # Portuguese
                'derecho a la tierra', 'conflicto de tierras',  # Spanish
                'droit foncier', 'conflit foncier'  # French
            ],
            'disease': [
                'cholera', 'malaria', 'disease', 'outbreak', 'epidemic', 'health crisis',
                'cólera', 'malária', 'doença', 'surto',  # Portuguese
                'cólera', 'malaria', 'enfermedad', 'brote',  # Spanish
                'choléra', 'paludisme', 'maladie', 'épidémie'  # French
            ],
            'development': [
                'development', 'redevelopment', 'urban renewal', 'regeneration',
                'desenvolvimento', 'renovação urbana',  # Portuguese
                'desarrollo', 'renovación urbana',  # Spanish
                'développement', 'rénovation urbaine'  # French
            ]
        }
        
        for event_type, keywords in event_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return event_type
        
        return 'other'
    
    def extract_affected_count(self, text):
        """Extract number of people mentioned"""
        if not text:
            return None
            
        patterns = [
            r'(\d+,?\d*)\s+(families|households|people|residents|persons|individuals)',
            r'(hundreds|thousands|millions)\s+(?:of\s+)?(families|households|people|residents)',
            r'(\d+,?\d*)\s+were\s+(evicted|displaced|affected|homeless)',
            r'over\s+(\d+,?\d*)\s+people',
            r'more than\s+(\d+,?\d*)\s+people',
            r'(\d+,?\d*)\s+to\s+(\d+,?\d*)\s+people',
            r'(\d+)\s+(evacuated|relocated|moved)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                num_str = match.group(1)
                if num_str.replace(',', '').isdigit():
                    return int(num_str.replace(',', ''))
                elif num_str == 'hundreds':
                    return 300
                elif num_str == 'thousands':
                    return 2000
                elif num_str == 'millions':
                    return 100000
        
        return None
    
    def process_articles(self, articles):
        """Process articles with database-only geocoding"""
        events = []
        
        print(f"\n📋 Processing {len(articles)} articles with database geocoding...\n")
        
        processed_count = 0
        geocoded_count = 0
        
        for i, article in enumerate(articles):
            if i % 20 == 0 and i > 0:
                print(f"   Processed {i}/{len(articles)} articles...")
            
            title = article.get('title', '')
            description = article.get('description', '')
            content = article.get('content', '')
            full_text = article.get('full_text', f"{title} {description} {content}")
            
            # Extract location from text
            slum_name, city, country, location_data = self.extract_location_from_text(full_text)
            
            if location_data:
                processed_count += 1
                geocoded_count += 1
                
                # Extract event details
                event_type = self.extract_event_type(full_text)
                affected_count = self.extract_affected_count(full_text)
                
                # Parse date
                raw_date = article.get('publishedAt', '')
                try:
                    if 'T' in raw_date:
                        published_date = raw_date.split('T')[0]
                    else:
                        published_date = raw_date[:10]
                except:
                    published_date = datetime.now().strftime('%Y-%m-%d')
                
                # Create display address
                if slum_name:
                    address = f"{slum_name.title()}, {location_data['city']}, {location_data['country']}"
                elif city:
                    address = f"{city.title()}, {location_data['country']}"
                else:
                    address = location_data['country']
                
                # Create event
                event = {
                    'title': title[:150],
                    'description': description[:200] if description else '',
                    'url': article.get('url', ''),
                    'date': published_date,
                    'source': article.get('source', {}).get('name', 'Unknown'),
                    'slum_name': slum_name,
                    'city': city,
                    'country': country,
                    'coordinates': {
                        'lat': location_data['lat'],
                        'lon': location_data['lon'],
                        'address': address,
                        'location_type': location_data.get('type', 'unknown')
                    },
                    'event_type': event_type,
                    'affected_count': affected_count,
                    'full_text': full_text,
                    'geocode_confidence': 'database',
                    'found_by_query': article.get('search_query', 'unknown')
                }
                
                events.append(event)
        
        print(f"\n📊 PROCESSING RESULTS:")
        print(f"   Total articles: {len(articles)}")
        print(f"   Articles with locations: {processed_count}")
        print(f"   Events ready to map: {len(events)}")
        
        # Statistics
        if events:
            event_types = [e['event_type'] for e in events]
            type_counts = Counter(event_types)
            
            print(f"\n🎯 EVENT TYPES:")
            for event_type, count in type_counts.most_common():
                print(f"   {event_type}: {count}")
            
            countries = [e['country'] for e in events if e['country']]
            country_counts = Counter(countries)
            
            print(f"\n🌍 COUNTRIES:")
            for country, count in country_counts.most_common(10):
                print(f"   {country}: {count}")
            
            # Show location types
            location_types = [e['coordinates']['location_type'] for e in events]
            location_type_counts = Counter(location_types)
            
            print(f"\n📍 LOCATION TYPES:")
            for loc_type, count in location_type_counts.most_common():
                print(f"   {loc_type}: {count}")
        
        return events
    
    def calculate_legend_intervals(self, event_counts):
        """Calculate dynamic legend intervals based on event counts"""
        if not event_counts:
            return [
                (1, 2, '#4dabf7', 'Low (1-2)'),
                (3, 5, '#ff922b', 'Medium (3-5)'),
                (6, 10, '#ff6b6b', 'High (6-10)'),
                (11, 1000, '#c92a2a', 'Critical (11+)')
            ]
        
        max_count = max(event_counts)
        
        # Adjust intervals based on maximum count
        if max_count <= 5:
            return [
                (1, 1, '#4dabf7', 'Single (1)'),
                (2, 3, '#ff922b', 'Few (2-3)'),
                (4, 5, '#ff6b6b', 'Several (4-5)')
            ]
        elif max_count <= 15:
            return [
                (1, 3, '#4dabf7', 'Low (1-3)'),
                (4, 7, '#ff922b', 'Medium (4-7)'),
                (8, 15, '#ff6b6b', 'High (8-15)')
            ]
        elif max_count <= 30:
            return [
                (1, 5, '#4dabf7', 'Low (1-5)'),
                (6, 15, '#ff922b', 'Medium (6-15)'),
                (16, 30, '#ff6b6b', 'High (16-30)')
            ]
        elif max_count <= 50:
            return [
                (1, 10, '#4dabf7', 'Low (1-10)'),
                (11, 25, '#ff922b', 'Medium (11-25)'),
                (26, 50, '#ff6b6b', 'High (26-50)')
            ]
        else:
            # For very high counts, use logarithmic scale
            third = max_count // 3
            return [
                (1, third, '#4dabf7', f'Low (1-{third})'),
                (third + 1, third * 2, '#ff922b', f'Medium ({third+1}-{third*2})'),
                (third * 2 + 1, max_count, '#ff6b6b', f'High ({third*2+1}+)')
            ]
    
    def create_html_map(self, events, output_file='slum_news_map.html'):
        """Create HTML map with refined visualization"""
        if not events:
            print("\n⚠️ No events to map!")
            return None
        
        # Calculate average coordinates
        valid_coords = [e for e in events if e['coordinates']['lat'] != 0 and e['coordinates']['lon'] != 0]
        if valid_coords:
            avg_lat = sum(e['coordinates']['lat'] for e in valid_coords) / len(valid_coords)
            avg_lon = sum(e['coordinates']['lon'] for e in valid_coords) / len(valid_coords)
        else:
            avg_lat, avg_lon = 20, 0
        
        # Prepare events JSON with proper date handling
        for event in events:
            # Ensure date is in proper format
            if 'date' in event and event['date']:
                try:
                    if isinstance(event['date'], str):
                        if 'T' in event['date']:
                            event['iso_date'] = event['date']
                            event['display_date'] = event['date'].split('T')[0]
                        else:
                            event['iso_date'] = event['date'] + "T00:00:00Z"
                            event['display_date'] = event['date']
                    else:
                        event['iso_date'] = datetime.now().isoformat() + "Z"
                        event['display_date'] = datetime.now().strftime('%Y-%m-%d')
                except:
                    event['iso_date'] = datetime.now().isoformat() + "Z"
                    event['display_date'] = datetime.now().strftime('%Y-%m-%d')
            else:
                event['iso_date'] = datetime.now().isoformat() + "Z"
                event['display_date'] = datetime.now().strftime('%Y-%m-%d')
        
        events_json = json.dumps(events, indent=2, ensure_ascii=False)
        
        # Statistics
        dates = [e['display_date'] for e in events if e.get('display_date')]
        if dates:
            date_range = f"{min(dates)} to {max(dates)}"
        else:
            date_range = "Unknown"
        
        # Count event types for bar chart (EXCLUDE "other" category)
        event_types = [e.get('event_type', 'other') for e in events]
        type_counts = Counter(event_types)
        
        # Filter out "other" for bar chart
        filtered_type_counts = {k: v for k, v in type_counts.items() if k != 'other'}
        
        # Prepare data for bar chart
        bar_chart_data = []
        if filtered_type_counts:
            max_count = max(filtered_type_counts.values()) if filtered_type_counts else 1
            
            for event_type, count in sorted(filtered_type_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / len(events)) * 100
                bar_chart_data.append({
                    'type': event_type,
                    'count': count,
                    'percentage': percentage,
                    'width': (count / max_count) * 100
                })
        
        # Calculate legend intervals
        location_groups = {}
        for event in events:
            key = f"{event['coordinates']['lat']:.4f},{event['coordinates']['lon']:.4f}"
            if key not in location_groups:
                location_groups[key] = []
            location_groups[key].append(event)
        
        event_counts = [len(group) for group in location_groups.values()]
        legend_intervals = self.calculate_legend_intervals(event_counts)
        
        # Generate legend HTML
        legend_html = ""
        for min_val, max_val, color, label in legend_intervals:
            legend_html += f"""
            <div class="legend-item">
                <div class="legend-circle" style="background-color: {color};"></div>
                <span>{label}</span>
            </div>
            """
        
        # Generate bar chart HTML
        bar_chart_html = ""
        for item in bar_chart_data:
            bar_chart_html += f"""
            <div class="bar-chart-row">
                <div class="bar-chart-label">{item['type']}</div>
                <div class="bar-chart-bar-container">
                    <div class="bar-chart-bar {item['type']}-bar" style="width: {item['width']}%"></div>
                    <div class="bar-chart-count">{item['count']} ({item['percentage']:.1f}%)</div>
                </div>
            </div>
            """
        
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>permanence.dev - Slum News Map</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; font-family: Arial, sans-serif; background: #1a1a1a; }}
        #map {{ height: 100vh; width: 100%; }}
        
        /* COMBINED LEFT PANEL - Info + Legend + Bar Chart */
        .left-panel {{
            position: absolute; top: 80px; left: 10px;
            background: rgba(30, 30, 30, 0.95); padding: 15px; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.5); z-index: 1000;
            max-width: 350px; border: 1px solid #444;
            max-height: 80vh; overflow-y: auto;
        }}
        .left-panel h2 {{ 
            margin: 0 0 15px 0; 
            font-size: 24px; 
            color: white; 
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
        .left-panel h4 {{ margin: 15px 0 10px 0; font-size: 14px; color: #e0e0e0; padding-top: 12px; border-top: 1px solid #444; }}
        .left-panel p {{ margin: 6px 0; font-size: 14px; line-height: 1.5; color: #e0e0e0; }}
        .stat {{ font-weight: bold; color: #ff6b6b; font-size: 16px; }}
        
        /* LEGEND ITEMS */
        .legend-item {{ 
            display: flex; align-items: center; margin: 6px 0; font-size: 12px; color: #ccc;
        }}
        .legend-circle {{
            width: 20px; height: 20px; border-radius: 50%;
            margin-right: 8px; border: 2px solid white;
        }}
        
        /* BAR CHART */
        .bar-chart-row {{
            display: flex; align-items: center; margin: 8px 0;
        }}
        .bar-chart-label {{
            width: 100px; font-size: 12px; color: #ccc; text-transform: capitalize;
        }}
        .bar-chart-bar-container {{
            flex-grow: 1; position: relative; height: 20px;
            background: #2a2a2a; border-radius: 3px; overflow: hidden;
        }}
        .bar-chart-bar {{
            height: 100%; transition: width 0.5s ease;
        }}
        .bar-chart-count {{
            position: absolute; right: 5px; top: 2px;
            font-size: 10px; color: white; font-weight: bold;
        }}
        
        /* Event type bar colors */
        .eviction-bar {{ background: linear-gradient(90deg, #ff6b6b, #ff8e8e); }}
        .demolition-bar {{ background: linear-gradient(90deg, #ff922b, #ffb347); }}
        .protest-bar {{ background: linear-gradient(90deg, #94d82d, #b2e057); }}
        .fire-bar {{ background: linear-gradient(90deg, #c92a2a, #e03131); }}
        .flood-bar {{ background: linear-gradient(90deg, #4dabf7, #74c0fc); }}
        .land_rights-bar {{ background: linear-gradient(90deg, #fcc419, #ffd43b); }}
        .disease-bar {{ background: linear-gradient(90deg, #cc5de8, #da77f2); }}
        .development-bar {{ background: linear-gradient(90deg, #339af0, #4dabf7); }}
        .other-bar {{ background: linear-gradient(90deg, #868e96, #adb5bd); }}
        
        /* SEARCH FILTER */
        .search-panel {{
            position: absolute; top: 10px; right: 10px;
            background: rgba(30, 30, 30, 0.95); padding: 15px; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.5); z-index: 1000;
            width: 320px; border: 1px solid #444;
        }}
        .search-panel h3 {{ margin: 0 0 10px 0; font-size: 16px; color: #e0e0e0; }}
        .search-box {{
            width: 100%; padding: 8px; font-size: 14px;
            border: 2px solid #555; border-radius: 4px;
            box-sizing: border-box; background: #2a2a2a; color: #e0e0e0;
        }}
        .search-box:focus {{
            outline: none; border-color: #ff6b6b;
        }}
        .filter-buttons {{
            margin-top: 10px; display: flex; gap: 5px; flex-wrap: wrap;
        }}
        .filter-btn {{
            padding: 6px 12px; font-size: 12px; border: 1px solid #555;
            background: #2a2a2a; border-radius: 4px; cursor: pointer;
            transition: all 0.2s; color: #e0e0e0;
        }}
        .filter-btn:hover {{ background: #3a3a3a; }}
        .filter-btn.active {{ background: #ff6b6b; color: white; border-color: #ff6b6b; }}
        .results-count {{
            margin-top: 10px; font-size: 13px; color: #999;
            padding-top: 8px; border-top: 1px solid #444;
        }}
        
        /* EVENT TYPE TAGS */
        .event-tag {{
            display: inline-block; padding: 3px 8px; border-radius: 12px;
            font-size: 11px; font-weight: bold; margin-right: 5px;
            text-transform: uppercase;
        }}
        .eviction-tag {{ background: #ff6b6b; color: white; }}
        .demolition-tag {{ background: #ff922b; color: white; }}
        .fire-tag {{ background: #c92a2a; color: white; }}
        .flood-tag {{ background: #4dabf7; color: white; }}
        .protest-tag {{ background: #94d82d; color: white; }}
        .land_rights-tag {{ background: #fcc419; color: black; }}
        .disease-tag {{ background: #cc5de8; color: white; }}
        .development-tag {{ background: #339af0; color: white; }}
        .other-tag {{ background: #868e96; color: white; }}
        
        /* POPUP - DARK MODE */
        .leaflet-popup-content-wrapper {{
            background: #2a2a2a !important;
            color: #e0e0e0 !important;
            border: 1px solid #444;
        }}
        .leaflet-popup-tip {{ background: #2a2a2a !important; }}
        .popup-content {{ min-width: 300px; max-width: 400px; }}
        .popup-content h3 {{ margin: 0 0 10px 0; font-size: 16px; color: #ff6b6b; }}
        .popup-content p {{ margin: 5px 0; font-size: 13px; line-height: 1.5; color: #e0e0e0; }}
        .popup-content a {{ color: #4dabf7; text-decoration: none; font-weight: bold; }}
        .popup-content a:hover {{ text-decoration: underline; }}
        .popup-content hr {{ border: none; border-top: 1px solid #444; }}
        .popup-meta {{ font-size: 12px; color: #999; }}
        
        /* DATA RANGE INFO */
        .data-info {{
            font-size: 11px; color: #999; margin-top: 8px; line-height: 1.4;
            border-top: 1px solid #333; padding-top: 8px;
        }}
    </style>
</head>
<body>
    <div class="left-panel">
        <h2>permanence.dev</h2>
        <p><strong>Total Events:</strong> <span class="stat">{len(events)}</span></p>
        <p><strong>Date Range:</strong><br>{date_range}</p>
        <p><strong>Event Types:</strong><br>
            {' '.join([f'<span class="event-tag {event_type}-tag">{event_type}</span>' for event_type in type_counts.keys()])}
        </p>
        <div class="data-info">
            Data Source: GDELT • {len(self.location_db)} locations<br>
            <small>Note: GDELT returns recent news (typically 0-7 days)</small>
        </div>
        
        <h4>📊 Event Intensity</h4>
        {legend_html}
        
        <h4>📈 Event Type Distribution</h4>
        <div style="margin-top: 10px;">
            {bar_chart_html if bar_chart_data else '<p style="color: #999; font-size: 12px;">No specific event types found (only "other")</p>'}
        </div>
    </div>

    <div class="search-panel">
        <h3>🔍 Filter News</h3>
        <input type="text" id="searchBox" class="search-box" placeholder="Search keywords...">
        <div class="filter-buttons">
            <button class="filter-btn active" onclick="filterBy('all')">All</button>
            <button class="filter-btn" onclick="filterBy('eviction')">Evictions</button>
            <button class="filter-btn" onclick="filterBy('demolition')">Demolitions</button>
            <button class="filter-btn" onclick="filterBy('protest')">Protests</button>
            <button class="filter-btn" onclick="filterBy('fire')">Fire</button>
            <button class="filter-btn" onclick="filterBy('flood')">Flood</button>
            <button class="filter-btn" onclick="filterBy('development')">Development</button>
            <button class="filter-btn" onclick="filterBy('other')">Other</button>
        </div>
        <div class="results-count">
            Showing <strong><span id="visibleCount">{len(events)}</span></strong> of {len(events)}
        </div>
        <div style="font-size: 12px; color: #999; margin-top: 8px;">
            Event types: {', '.join([f'{k}: {v}' for k, v in type_counts.items()])}
        </div>
    </div>

    <div id="map"></div>

    <script>
        const eventsData = {events_json};
        const map = L.map('map').setView([{avg_lat}, {avg_lon}], 2);

        // DARK MODE TILES - CartoDB Dark Matter
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
        }}).addTo(map);

        // Store all markers and filtered markers
        let allMarkers = [];
        let currentFilter = 'all';
        let currentSearch = '';

        // Function to create markers for a given set of events
        function createMarkers(events) {{
            // Clear existing markers
            allMarkers.forEach(marker => map.removeLayer(marker));
            allMarkers = [];
            
            if (events.length === 0) {{
                document.getElementById('visibleCount').textContent = 0;
                return;
            }}
            
            // Group events by location
            const locationGroups = {{}};
            events.forEach(event => {{
                const key = `${{event.coordinates.lat.toFixed(4)}},${{event.coordinates.lon.toFixed(4)}}`;
                if (!locationGroups[key]) {{
                    locationGroups[key] = {{
                        location: event.coordinates.address,
                        coords: event.coordinates,
                        events: []
                    }};
                }}
                locationGroups[key].events.push(event);
            }});
            
            // Calculate dynamic legend intervals
            const eventCounts = Object.values(locationGroups).map(group => group.events.length);
            const maxCount = Math.max(...eventCounts);
            
            function getIntensityColor(count) {{
                if (maxCount <= 5) {{
                    if (count <= 1) return '#4dabf7';
                    if (count <= 3) return '#ff922b';
                    return '#ff6b6b';
                }} else if (maxCount <= 15) {{
                    if (count <= 3) return '#4dabf7';
                    if (count <= 7) return '#ff922b';
                    return '#ff6b6b';
                }} else if (maxCount <= 30) {{
                    if (count <= 5) return '#4dabf7';
                    if (count <= 15) return '#ff922b';
                    return '#ff6b6b';
                }} else if (maxCount <= 50) {{
                    if (count <= 10) return '#4dabf7';
                    if (count <= 25) return '#ff922b';
                    return '#ff6b6b';
                }} else {{
                    const third = Math.floor(maxCount / 3);
                    if (count <= third) return '#4dabf7';
                    if (count <= third * 2) return '#ff922b';
                    return '#ff6b6b';
                }}
            }}
            
            // Function to get tag class for event type
            function getEventTagClass(eventType) {{
                return eventType + '-tag';
            }}
            
            // Function to format date properly
            function formatDate(dateStr) {{
                if (!dateStr) return 'Unknown date';
                try {{
                    const date = new Date(dateStr);
                    if (isNaN(date.getTime())) return dateStr;
                    return date.toLocaleDateString('en-US', {{ 
                        year: 'numeric', 
                        month: 'short', 
                        day: 'numeric' 
                    }});
                }} catch (e) {{
                    return dateStr;
                }}
            }}
            
            // Create markers
            Object.values(locationGroups).forEach(group => {{
                const eventCount = group.events.length;
                const totalAffected = group.events.reduce((sum, e) => sum + (e.affected_count || 0), 0);
                const intensityColor = getIntensityColor(eventCount);
                
                // Improved scaling: Use logarithmic scale for better differentiation
                const minSize = 25;
                const maxSize = 120;
                const size = Math.min(maxSize, minSize + (Math.log(eventCount + 1) * 25));
                
                // Add transparency (0.7 opacity)
                const iconHtml = `
                    <div style="
                        background-color: ${{intensityColor}};
                        width: ${{size}}px;
                        height: ${{size}}px;
                        border-radius: 50%;
                        border: 3px solid rgba(255, 255, 255, 0.9);
                        box-shadow: 0 4px 12px rgba(0,0,0,0.6);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: ${{Math.min(22, 14 + Math.log(eventCount + 1) * 3)}}px;
                        color: white;
                        font-weight: bold;
                        opacity: 0.7;
                        transition: opacity 0.3s ease;
                    " 
                    onmouseover="this.style.opacity='0.9'" 
                    onmouseout="this.style.opacity='0.7'"
                    >${{eventCount}}</div>
                `;
                
                const customIcon = L.divIcon({{
                    html: iconHtml,
                    className: 'custom-marker',
                    iconSize: [size, size],
                    iconAnchor: [size/2, size/2],
                    popupAnchor: [0, -size/2]
                }});
                
                let popupContent = `
                    <div class="popup-content">
                        <h3>📍 ${{group.location}}</h3>
                        <p><strong>${{eventCount}} news item${{eventCount > 1 ? 's' : ''}}</strong></p>
                        ${{totalAffected > 0 ? `<p>👥 Total affected: <strong>${{totalAffected.toLocaleString()}}</strong></p>` : ''}}
                        <hr style="margin: 10px 0; border: none; border-top: 1px solid #444;">
                `;
                
                group.events.forEach((event, idx) => {{
                    const eventTag = event.event_type ? 
                        `<span class="event-tag ${{getEventTagClass(event.event_type)}}">${{event.event_type}}</span>` : '';
                    
                    popupContent += `
                        <div style="margin: 10px 0; padding: 10px 0; ${{idx > 0 ? 'border-top: 1px solid #444;' : ''}}">
                            ${{eventTag}}
                            <p style="margin: 5px 0 5px 0;"><strong>${{event.title}}</strong></p>
                            <p class="popup-meta">
                                📅 ${{formatDate(event.iso_date)}}
                                ${{event.source && event.source !== 'Unknown' ? `• 📰 ${{event.source}}` : ''}}
                            </p>
                            ${{event.affected_count ? `<p style="margin: 3px 0; font-size: 12px; color: #ff6b6b;">👥 ${{event.affected_count.toLocaleString()}} people affected</p>` : ''}}
                            <p style="margin: 5px 0 0 0;">
                                <a href="${{event.url}}" target="_blank">Read article →</a>
                            </p>
                        </div>
                    `;
                }});
                
                popupContent += `</div>`;
                
                const marker = L.marker([group.coords.lat, group.coords.lon], {{ icon: customIcon }})
                    .bindPopup(popupContent, {{ maxWidth: 400, maxHeight: 500 }});
                
                marker.addTo(map);
                allMarkers.push(marker);
            }});
            
            document.getElementById('visibleCount').textContent = events.length;
        }}
        
        // Initial creation of markers with all events
        createMarkers(eventsData);
        
        // FILTERING FUNCTIONALITY
        function applyFilters() {{
            let filteredEvents = eventsData;
            
            // Apply event type filter
            if (currentFilter !== 'all') {{
                filteredEvents = filteredEvents.filter(event => 
                    event.event_type === currentFilter
                );
            }}
            
            // Apply search filter
            if (currentSearch) {{
                filteredEvents = filteredEvents.filter(event => 
                    event.full_text.toLowerCase().includes(currentSearch.toLowerCase()) ||
                    event.title.toLowerCase().includes(currentSearch.toLowerCase())
                );
            }}
            
            createMarkers(filteredEvents);
        }}
        
        // Search box event
        document.getElementById('searchBox').addEventListener('input', function(e) {{
            currentSearch = e.target.value;
            applyFilters();
            
            // Remove active class from filter buttons when searching
            document.querySelectorAll('.filter-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
        }});
        
        // Preset filter buttons
        function filterBy(eventType) {{
            // Update button states
            document.querySelectorAll('.filter-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            event.target.classList.add('active');
            
            // Clear search box when filter is applied
            document.getElementById('searchBox').value = '';
            currentSearch = '';
            
            // Set current filter and apply
            currentFilter = eventType;
            applyFilters();
        }}
        
        map.on('popupopen', function(e) {{
            map.setView(e.popup.getLatLng(), Math.max(map.getZoom(), 6), {{ animate: true }});
        }});
    </script>
</body>
</html>"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"\n✅ Map saved: {output_file}")
        return output_file


def main():
    print("=" * 100)
    print("                     permanence.dev - Slum News Mapper")
    print("          GDELT Only • Full Date Range • Dynamic Legend • Bar Chart • 200+ Locations")
    print("=" * 100)
    
    mapper = RefinedSlumMapper()
    
    print(f"\n🏘️  Database: {len(mapper.location_db)} locations (slums, cities, countries)")
    print(f"🌐 Sources: GDELT only")
    print(f"📅 Searching all available dates (no date restriction)\n")
    
    # Search GDELT only
    articles = mapper.search_gdelt_only()
    
    if not articles:
        print("\n❌ No articles found from GDELT!")
        print("   Try adjusting search terms or check your internet connection.")
        return
    
    # Process articles with database geocoding
    events = mapper.process_articles(articles)
    
    if not events:
        print("\n❌ No events could be mapped!")
        print("   No articles contained recognizable location names.")
        return
    
    print("\n" + "=" * 100)
    print(f"🗺️  SUCCESSFULLY MAPPED {len(events)} NEWS ITEMS")
    print("=" * 100)
    
    # Save data (JSON only for now - CSV generation disabled)
    with open('slum_news_data.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    print("\n✅ Data saved: slum_news_data.json")
    
    # CSV generation DISABLED for simplified workflow
    # Uncomment below if you want CSV files later:
    # df_data = []
    # for event in events:
    #     df_data.append({
    #         'Title': event['title'],
    #         'Date': event['date'],
    #         'Source': event['source'],
    #         'Event Type': event['event_type'],
    #         'Slum': event['slum_name'],
    #         'City': event['city'],
    #         'Country': event['country'],
    #         'Location': event['coordinates']['address'],
    #         'Latitude': event['coordinates']['lat'],
    #         'Longitude': event['coordinates']['lon'],
    #         'People Affected': event['affected_count'],
    #         'URL': event['url'],
    #         'Geocode Source': 'database'
    #     })
    # 
    # df = pd.DataFrame(df_data)
    # df.to_csv('slum_news_data.csv', index=False, encoding='utf-8')
    # print("✅ Data saved: slum_news_data.csv")
    
    # Create HTML map
    mapper.create_html_map(events)
    
    # Detailed statistics
    print("\n📊 DETAILED STATISTICS:")
    print("=" * 100)
    
    # Sources
    sources = [e['source'] for e in events]
    source_counts = Counter(sources)
    
    print("\n📰 TOP SOURCES:")
    for source, count in source_counts.most_common(10):
        print(f"   {source}: {count}")
    
    # Event types
    event_types = [e['event_type'] for e in events]
    type_counts = Counter(event_types)
    
    print("\n🎯 EVENT TYPES:")
    for event_type, count in type_counts.most_common():
        print(f"   {event_type}: {count}")
    
    # Locations
    locations = [e['coordinates']['address'] for e in events]
    location_counts = Counter(locations)
    
    print("\n📍 TOP LOCATIONS:")
    for location, count in location_counts.most_common(10):
        print(f"   {location}: {count}")
    
    print("\n" + "=" * 100)
    print("✅ SUCCESS! Files created:")
    print("   - slum_news_map.html (interactive map with bar chart)")
    print("   - slum_news_data.json (complete data)")
    print("\n📌 FEATURES:")
    print("   • Removed date restrictions from GDELT queries")
    print("   • 'Other' category can now be filtered separately")
    print("   • Brand name: 'permanence.dev' (white, larger)")
    print("   • Enhanced filtering: clicking a filter shows ONLY that event type")
    print("   • Simplified version: CSV generation disabled")
    print("=" * 100)


if __name__ == "__main__":
    main()
