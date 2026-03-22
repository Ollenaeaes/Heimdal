-- Fix newline-corrupted flag_country and class_society values from PDF extraction.

-- Fix flag_country: normalize known multi-word country names
UPDATE vessel_profiles SET flag_country = 'MH' WHERE flag_country LIKE 'MARSHALL%ISLANDS';
UPDATE vessel_profiles SET flag_country = 'SL' WHERE flag_country LIKE 'SIERRA%LEONE';
UPDATE vessel_profiles SET flag_country = 'HK' WHERE flag_country LIKE 'HONG%KONG%';
UPDATE vessel_profiles SET flag_country = 'GQ' WHERE flag_country LIKE 'EQUATORIAL%GUINEA';
UPDATE vessel_profiles SET flag_country = 'KY' WHERE flag_country LIKE 'CAYMAN%ISLANDS';
UPDATE vessel_profiles SET flag_country = 'PT' WHERE flag_country LIKE 'PORTUGAL%';
UPDATE vessel_profiles SET flag_country = 'GW' WHERE flag_country LIKE 'GUINEA-%BISSAU';
UPDATE vessel_profiles SET flag_country = 'ST' WHERE flag_country LIKE 'SAO%TOME%';
UPDATE vessel_profiles SET flag_country = 'MM' WHERE flag_country LIKE 'MYANMAR%';
-- Remove trailing "FALSE" from PDF boolean column bleed
UPDATE vessel_profiles SET flag_country = 'CM' WHERE flag_country LIKE 'CAMEROON%FALSE';
UPDATE vessel_profiles SET flag_country = 'GY' WHERE flag_country LIKE 'GUYANA%FALSE';
UPDATE vessel_profiles SET flag_country = 'MG' WHERE flag_country LIKE 'MADAGASC%FALSE';

-- Fix class_society: take only the first abbreviation (primary class)
UPDATE vessel_profiles
SET class_society = split_part(replace(replace(class_society, chr(10), ' '), chr(13), ' '), ' ', 1)
WHERE class_society LIKE '%' || chr(10) || '%';

-- Strip any remaining newlines from all text fields
UPDATE vessel_profiles
SET flag_country = replace(replace(flag_country, chr(10), ' '), chr(13), ' ')
WHERE flag_country LIKE '%' || chr(10) || '%';
