# -*- coding: utf-8 -*-
"""Frozen catalogue IDs shared by PostgreSQL historian and SQLite SAF catalog.

DO NOT reorder or renumber existing entries. Only APPEND new variables/units
with the next free id. These ids must stay identical across every edge DB
(first boot, upgrade, and SAF re-hydrate).

Unit ``name`` values must be unique (DB constraint). Volume symbol ``lt`` uses
name ``liter`` to avoid clashing with VolumetricFlow ``liter_sec`` (``lt/sec``).
"""
from __future__ import annotations

# (id, name)
STABLE_VARIABLES: tuple[tuple[int, str], ...] = (
    (1, 'Temperature'),
    (2, 'Length'),
    (3, 'Current'),
    (4, 'Time'),
    (5, 'Pressure'),
    (6, 'Mass'),
    (7, 'Force'),
    (8, 'Power'),
    (9, 'VolumetricFlow'),
    (10, 'MassFlow'),
    (11, 'Density'),
    (12, 'Percentage'),
    (13, 'Adimentional'),
    (14, 'Volume'),
    (15, 'DataSize'),
)

# (id, name, symbol, variable_id)
STABLE_UNITS: tuple[tuple[int, str, str, int], ...] = (
    (1, 'degKelvin', 'K', 1),  # Temperature
    (2, 'degCelsius', 'C', 1),  # Temperature
    (3, 'degRankine', 'R', 1),  # Temperature
    (4, 'degFarenheit', 'F', 1),  # Temperature
    (5, 'fm', 'fm', 2),  # Length
    (6, 'pm', 'pm', 2),  # Length
    (7, 'nm', 'nm', 2),  # Length
    (8, 'um', 'um', 2),  # Length
    (9, 'mm', 'mm', 2),  # Length
    (10, 'cm', 'cm', 2),  # Length
    (11, 'm', 'm', 2),  # Length
    (12, 'dam', 'dam', 2),  # Length
    (13, 'hm', 'hm', 2),  # Length
    (14, 'km', 'km', 2),  # Length
    (15, 'Mm', 'Mm', 2),  # Length
    (16, 'Gm', 'Gm', 2),  # Length
    (17, 'Tm', 'Tm', 2),  # Length
    (18, 'Pm', 'Pm', 2),  # Length
    (19, 'inch', 'inch', 2),  # Length
    (20, 'ft', 'ft', 2),  # Length
    (21, 'yd', 'yd', 2),  # Length
    (22, 'mi', 'mi', 2),  # Length
    (23, 'nautMi', 'nautMi', 2),  # Length
    (24, 'lightYear', 'lightYear', 2),  # Length
    (25, 'A', 'A', 3),  # Current
    (26, 'mA', 'mA', 3),  # Current
    (27, 'kA', 'kA', 3),  # Current
    (28, 'ms', 'ms', 4),  # Time
    (29, 's', 's', 4),  # Time
    (30, 'minute', 'minute', 4),  # Time
    (31, 'hr', 'hr', 4),  # Time
    (32, 'day', 'day', 4),  # Time
    (33, 'bar', 'bar', 5),  # Pressure
    (34, 'mbar', 'mbar', 5),  # Pressure
    (35, 'ubar', 'ubar', 5),  # Pressure
    (36, 'Pa', 'Pa', 5),  # Pressure
    (37, 'hPa', 'hPa', 5),  # Pressure
    (38, 'kPa', 'kPa', 5),  # Pressure
    (39, 'MPa', 'MPa', 5),  # Pressure
    (40, 'kgcm2', 'kgcm2', 5),  # Pressure
    (41, 'atm', 'atm', 5),  # Pressure
    (42, 'mmHg', 'mmHg', 5),  # Pressure
    (43, 'mmH2O', 'mmH2O', 5),  # Pressure
    (44, 'mH2O', 'mH2O', 5),  # Pressure
    (45, 'psi', 'psi', 5),  # Pressure
    (46, 'ftH2O', 'ftH2O', 5),  # Pressure
    (47, 'inH2O', 'inH2O', 5),  # Pressure
    (48, 'inHg', 'inHg', 5),  # Pressure
    (49, 'kg', 'kg', 6),  # Mass
    (50, 'g', 'g', 6),  # Mass
    (51, 'mg', 'mg', 6),  # Mass
    (52, 'lb', 'lb', 6),  # Mass
    (53, 'metricTon', 'metricTon', 6),  # Mass
    (54, 'oz', 'oz', 6),  # Mass
    (55, 'grain', 'grain', 6),  # Mass
    (56, 'shortTon', 'shortTon', 6),  # Mass
    (57, 'longTon', 'longTon', 6),  # Mass
    (58, 'slug', 'slug', 6),  # Mass
    (59, 'N', 'N', 7),  # Force
    (60, 'kN', 'kN', 7),  # Force
    (61, 'MN', 'MN', 7),  # Force
    (62, 'GN', 'GN', 7),  # Force
    (63, 'gf', 'gf', 7),  # Force
    (64, 'kgf', 'kgf', 7),  # Force
    (65, 'dyn', 'dyn', 7),  # Force
    (66, 'Jm', 'J/m', 7),  # Force
    (67, 'Jcm', 'J/cm', 7),  # Force
    (68, 'shortTonF', 'shortTonF', 7),  # Force
    (69, 'longTonF', 'longTonF', 7),  # Force
    (70, 'kipf', 'kipf', 7),  # Force
    (71, 'lbf', 'lbf', 7),  # Force
    (72, 'ozf', 'ozf', 7),  # Force
    (73, 'pdl', 'pdl', 7),  # Force
    (74, 'kW', 'kW', 8),  # Power
    (75, 'BTU_hr', 'BTU/hr', 8),  # Power
    (76, 'BTU_min', 'BTU/min', 8),  # Power
    (77, 'BTU_sec', 'BTU/sec', 8),  # Power
    (78, 'cal_sec', 'cal/sec', 8),  # Power
    (79, 'cal_min', 'cal/min', 8),  # Power
    (80, 'cal_hr', 'cal/hr', 8),  # Power
    (81, 'erg_sec', 'erg/sec', 8),  # Power
    (82, 'erg_min', 'erg/min', 8),  # Power
    (83, 'erg_hr', 'erg/hr', 8),  # Power
    (84, 'ftlb_sec', 'ftlb/sec', 8),  # Power
    (85, 'GW', 'GW', 8),  # Power
    (86, 'MW', 'MW', 8),  # Power
    (87, 'kCal_sec', 'kCal/sec', 8),  # Power
    (88, 'kCal_min', 'kCal/min', 8),  # Power
    (89, 'kCal_hr', 'kCal/hr', 8),  # Power
    (90, 'mW', 'mW', 8),  # Power
    (91, 'W', 'W', 8),  # Power
    (92, 'VA', 'VA', 8),  # Power
    (93, 'hp_mech', 'hp_mech', 8),  # Power
    (94, 'hp_ele', 'hp_ele', 8),  # Power
    (95, 'hp_metric', 'hp_metric', 8),  # Power
    (96, 'metric_ton_ref', 'metric_ton_ref', 8),  # Power
    (97, 'US_ton_ref', 'US_ton_ref', 8),  # Power
    (98, 'J_sec', 'J/sec', 8),  # Power
    (99, 'J_min', 'J/min', 8),  # Power
    (100, 'J_hr', 'J/hr', 8),  # Power
    (101, 'kgfm_sec', 'kgf-m/sec', 8),  # Power
    (102, 'bbl_day', 'bbl/day', 9),  # VolumetricFlow
    (103, 'bbl_hr', 'bbl/hr', 9),  # VolumetricFlow
    (104, 'bbl_min', 'bbl/min', 9),  # VolumetricFlow
    (105, 'bbl_sec', 'bbl/sec', 9),  # VolumetricFlow
    (106, 'gal_day', 'gal/day', 9),  # VolumetricFlow
    (107, 'gal_hr', 'gal/hr', 9),  # VolumetricFlow
    (108, 'gal_min', 'gal/min', 9),  # VolumetricFlow
    (109, 'gal_sec', 'gal/sec', 9),  # VolumetricFlow
    (110, 'cubic_meter_day', 'm3/day', 9),  # VolumetricFlow
    (111, 'cubic_meter_hr', 'm3/hr', 9),  # VolumetricFlow
    (112, 'cubic_meter_min', 'm3/min', 9),  # VolumetricFlow
    (113, 'cubic_meter_sec', 'm3/sec', 9),  # VolumetricFlow
    (114, 'liter_day', 'lt/day', 9),  # VolumetricFlow
    (115, 'liter_hr', 'lt/hr', 9),  # VolumetricFlow
    (116, 'liter_min', 'lt/min', 9),  # VolumetricFlow
    (117, 'liter_sec', 'lt/sec', 9),  # VolumetricFlow
    (118, 'cubic_centimeter_day', 'cc/day', 9),  # VolumetricFlow
    (119, 'cubic_centimeter_hr', 'cc/hr', 9),  # VolumetricFlow
    (120, 'cubic_centimeter_min', 'cc/min', 9),  # VolumetricFlow
    (121, 'cubic_centimeter_sec', 'cc/sec', 9),  # VolumetricFlow
    (122, 'kg_day', 'kg/day', 10),  # MassFlow
    (123, 'kg_hr', 'kg/hr', 10),  # MassFlow
    (124, 'kg_min', 'kg/min', 10),  # MassFlow
    (125, 'kg_sec', 'kg/sec', 10),  # MassFlow
    (126, 'g_day', 'g/day', 10),  # MassFlow
    (127, 'g_hr', 'g/hr', 10),  # MassFlow
    (128, 'g_min', 'g/min', 10),  # MassFlow
    (129, 'g_sec', 'g/sec', 10),  # MassFlow
    (130, 'mg_day', 'mg/day', 10),  # MassFlow
    (131, 'mg_hr', 'mg/hr', 10),  # MassFlow
    (132, 'mg_min', 'mg/min', 10),  # MassFlow
    (133, 'mg_sec', 'mg/sec', 10),  # MassFlow
    (134, 'lb_day', 'lb/day', 10),  # MassFlow
    (135, 'lb_hr', 'lb/hr', 10),  # MassFlow
    (136, 'lb_min', 'lb/min', 10),  # MassFlow
    (137, 'lb_sec', 'lb/sec', 10),  # MassFlow
    (138, 'metricTon_day', 'metricTon/day', 10),  # MassFlow
    (139, 'metricTon_hr', 'metricTon/hr', 10),  # MassFlow
    (140, 'metricTon_min', 'metricTon/min', 10),  # MassFlow
    (141, 'metricTon_sec', 'metricTon/sec', 10),  # MassFlow
    (142, 'kg_bbl', 'kg/bbl', 11),  # Density
    (143, 'kg_gal', 'kg/gal', 11),  # Density
    (144, 'kg_m3', 'kg/m3', 11),  # Density
    (145, 'kg_lt', 'kg/lt', 11),  # Density
    (146, 'kg_ml', 'kg/ml', 11),  # Density
    (147, 'g_bbl', 'g/bbl', 11),  # Density
    (148, 'g_gal', 'g/gal', 11),  # Density
    (149, 'g_m3', 'g/m3', 11),  # Density
    (150, 'g_lt', 'g/lt', 11),  # Density
    (151, 'g_ml', 'g/ml', 11),  # Density
    (152, 'mg_bbl', 'mg/bbl', 11),  # Density
    (153, 'mg_gal', 'mg/gal', 11),  # Density
    (154, 'mg_m3', 'kmg/m3', 11),  # Density
    (155, 'mg_lt', 'mg/lt', 11),  # Density
    (156, 'mg_ml', 'mg/ml', 11),  # Density
    (157, 'lb_bbl', 'lb/bbl', 11),  # Density
    (158, 'lb_gal', 'lb/gal', 11),  # Density
    (159, 'lb_m3', 'lb/m3', 11),  # Density
    (160, 'lb_lt', 'lb/lt', 11),  # Density
    (161, 'lb_ml', 'lb/ml', 11),  # Density
    (162, 'metricTon_bbl', 'metricTon/bbl', 11),  # Density
    (163, 'metricTon_gal', 'metricTon/gal', 11),  # Density
    (164, 'metricTon_m3', 'metricTon/m3', 11),  # Density
    (165, 'metricTon_lt', 'metricTon/lt', 11),  # Density
    (166, 'metricTon_ml', 'metricTon/ml', 11),  # Density
    (167, 'percentage', '%', 12),  # Percentage
    (168, 'adim', 'adim', 13),  # Adimentional
    (169, 'bbl', 'bbl', 14),  # Volume
    (170, 'gal', 'gal', 14),  # Volume
    (171, 'cubic_meter', 'm3', 14),  # Volume
    (172, 'liter', 'lt', 14),  # Volume
    (173, 'milliliter', 'ml', 14),  # Volume
    (174, 'byte', 'B', 15),  # DataSize
    (175, 'kibibyte', 'kB', 15),  # DataSize
    (176, 'mebibyte', 'MB', 15),  # DataSize
    (177, 'gibibyte', 'GB', 15),  # DataSize
)

STABLE_UNIT_ID_BY_SYMBOL: dict[str, int] = {symbol: uid for uid, _n, symbol, _v in STABLE_UNITS}
STABLE_VARIABLE_ID_BY_NAME: dict[str, int] = {name: vid for vid, name in STABLE_VARIABLES}
STABLE_UNIT_ID_MAX = 177
STABLE_VARIABLE_ID_MAX = 15
