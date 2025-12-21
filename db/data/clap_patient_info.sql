-- MySQL dump 10.13  Distrib 8.0.43, for Win64 (x86_64)
--
-- Host: localhost    Database: clap
-- ------------------------------------------------------
-- Server version	8.0.43

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `patient_info`
--

DROP TABLE IF EXISTS `patient_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `patient_info` (
  `PATIENT_ID` char(4) NOT NULL,
  `CODE` char(4) NOT NULL,
  `NAME` varchar(50) DEFAULT NULL,
  `AGE` smallint DEFAULT NULL,
  `SEX` char(1) DEFAULT NULL,
  `EDU` smallint DEFAULT NULL,
  `EXCLUDED` char(1) DEFAULT '0',
  `POST_STROKE_DATE` date DEFAULT NULL,
  `DIAGNOSIS` varchar(100) DEFAULT NULL,
  `STROKE_TYPE` char(1) DEFAULT NULL,
  `LESION_LOCATION` varchar(100) DEFAULT NULL,
  `HEMIPLEGIA` varchar(5) DEFAULT NULL,
  `HEMINEGLECT` varchar(5) DEFAULT NULL,
  `VISUAL_FIELD_DEFECT` varchar(5) DEFAULT NULL,
  `CREATE_DATE` datetime DEFAULT CURRENT_TIMESTAMP,
  `UPDATE_DATE` datetime DEFAULT NULL,
  PRIMARY KEY (`PATIENT_ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='환자 정보';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `patient_info`
--

LOCK TABLES `patient_info` WRITE;
/*!40000 ALTER TABLE `patient_info` DISABLE KEYS */;
INSERT INTO `patient_info` (`PATIENT_ID`,`CODE`,`AGE`,`SEX`,`EDU`,`EXCLUDED`,`POST_STROKE_DATE`,`DIAGNOSIS`,`STROKE_TYPE`,`LESION_LOCATION`,`HEMIPLEGIA`,`HEMINEGLECT`,`VISUAL_FIELD_DEFECT`) VALUES
('1001', '7M9V', '43', '0', '16', '0', '2022-10-25', '1', '2', '10022863', '2', NULL, NULL),
('1002', '4G3J', '0', '1', NULL, '1', NULL, NULL, NULL, NULL, NULL, NULL, NULL),
('1003', '1F0U', '78', '1', '6', '0', '2025-01-27', '0', '0', '07808919', '2', NULL, NULL),
('1004', '4S7Q', '69', '1', '12', '0', '2025-02-03', NULL, NULL, '06065924', NULL, NULL, NULL),
('1005', '1U8W', '0', NULL, NULL, '1', NULL, NULL, NULL, NULL, NULL, NULL, NULL),
('2006', '7G5U', '58', '0', '12', '0', '2024-10-04', '독성뇌병증', NULL, '씨엔씨', NULL, '2', '2'),
('2007', '4Q2M', '66', '0', '12', '0', '2024-11-18', '0', NULL, '씨엔씨', NULL, '2', '2'),
('3008', '2V2T', '55', '0', '16', '0', '2024-03-03', '0', '1', 'Lt. cerebral infaction', '0', '2', '2'),
('3009', '7M1P', '70', '0', '16', '0', '2023-09-30', '1', '1', 'Lt. BG & CR ICH', '0', '2', '2'),
('3010', '1T1D', '64', '0', '12', '0', '2024-12-01', '3', NULL, 'Pakinson disease', '2', '2', '2'),
('3011', '1I0O', '28', '1', '16', '0', '2024-01-01', '1', NULL, 'cerebellar ICH', '1', '2', '2'),
('3012', '3A6L', '0', '0', '12', '1', '2024-09-22', '0', '1', 'Lt. MCA ACA infaction', '0', '2', '2'),
('3013', '6D8M', '0', '0', '12', '1', '2023-12-25', '0', '1', 'Lt. MCA ACA infaction', '0', '2', '2'),
('2014', '0Q9O', '77', '1', '6', '0', NULL, NULL, NULL, '씨엔씨', NULL, '2', '2'),
('1015', '3Q9V', '46', '1', '16', '0', NULL, '1', '1', '03614916', NULL, NULL, NULL),
('3016', '3S6C', '64', '0', '12', '1', NULL, NULL, NULL, NULL, NULL, NULL, NULL),
('3017', '9W1L', '59', '0', '12', '0', '2024-09-26', '1', NULL, '첼로', '0', '2', '2'),
('3018', '3C5H', '44', '1', '12', '0', '2024-01-13', '0', NULL, '첼로', NULL, '2', '2'),
('3019', '5X7Q', '65', '0', '12', '0', '2024-08-31', '1', NULL, '첼로', '0', '2', '2'),
('3020', '2L3N', '69', '1', '6', '0', '2024-06-21', '0', NULL, '첼로', '0', '2', '2'),
('3021', '4L3K', '0', '1', NULL, '1', NULL, NULL, NULL, NULL, NULL, NULL, NULL),
('3022', '3C3X', '72', '0', '9', '0', '2023-09-08', '1', NULL, '첼로', '0', '2', '2'),
('1023', '8E9F', '69', '1', '12', '0', '2006-10-08', '1', '1', '00776383', '0', NULL, NULL),
('1024', '2C9R', '64', '0', '6', '0', '2025-02-13', '0', '0', '10454901', '2', NULL, NULL),
('1025', '1D0C', '69', '1', '6', '0', '2025-02-13', '0', '1', '08970846', '2', NULL, NULL),
('1026', '7K3N', '63', '0', '14', '0', '2025-02-14', '0', '0', '05418877', '2', NULL, NULL),
('1027', '6X6O', '86', '0', '12', '0', '2025-02-14', '0', '2', '10471987', '2', NULL, NULL),
('3028', '2A9R', '66', '0', '16', '0', '2024-02-23', '1', NULL, 'ICH', '0', '2', '2'),
('3029', '3E8N', '72', '1', '6', '0', '2024-07-06', '0', '1', 'Lt. BG infaction', '0', '2', '2'),
('3030', '7U8T', '69', '0', '16', '0', '2024-09-10', '0', '1', 'Lt. MCA infaction', '0', '2', '2'),
('1031', '6Q8A', '0', '1', '16', '1', NULL, NULL, NULL, NULL, NULL, NULL, NULL),
('1032', '3U7O', '73', '0', '12', '0', '2025-02-14', '0', '2', '10601137', '2', NULL, NULL),
('1033', '2O3N', '72', '1', '16', '0', '2025-02-20', '0', '0', '10601442', '1', NULL, NULL),
('1034', '5Q5T', '76', '0', '12', '0', '2025-02-20', '0', '0', '10572319', '0', NULL, NULL),
('1035', '6T9I', '80', '0', '12', '0', '2025-01-27', '0', '1', '01604557', '2', NULL, NULL),
('1036', '1Z5J', '56', '1', '12', '0', '2024-10-25', '0', '0', '10594460', '2', NULL, NULL),
('3037', '9W7A', '67', '1', '9', '0', '2023-12-21', '0', '1', 'Lt. MCA infaction, Lt. high frontal lobe infaction', '0', '2', '2'),
('3038', '5J3O', '47', '0', '12', '0', '2024-06-22', '0', NULL, 'MCA infaction', '0', '2', '2'),
('3039', '8A0D', '61', '0', '16', '0', '2024-02-22', '1', NULL, 'cbr ICH', '1', '2', '2'),
('3040', '7I6T', '69', '1', '16', '0', '2024-11-28', '1', '1', 'Lt. ACA MCA infaction', '0', '2', '2'),
('3041', '7S3C', '65', '1', '6', '0', '2024-06-02', '1', NULL, 'SAH w P-comAn rupuro ', '1', '2', '2'),
('1042', '2L7W', '62', '1', '12', '0', '2025-02-24', '0', '1', '04877178', '2', NULL, NULL),
('1043', '3X2K', '70', '0', '9', '0', '2025-02-22', '0', '2', '01499595', '0', NULL, NULL),
('1044', '5C3E', '0', '0', NULL, '1', NULL, NULL, NULL, NULL, NULL, NULL, NULL),
('1045', '2Z1E', '65', '0', '16', '0', '2023-05-05', '1', '2', '01631397', '2', NULL, NULL),
('4046', '2V4P', '64', '0', '6', '1', '2024-12-26', '0', '1', '아이엠', '0', '2', '2'),
('4047', '2E3G', '52', '0', '9', '1', '2024-09-30', '1', NULL, '아이엠', '2', '2', '2'),
('4048', '1V9X', '55', '0', '16', '0', '2025-01-17', '1', '0', '아이엠', '1', '2', '2'),
('4049', '3V4A', '74', '1', '6', '0', '2024-08-08', '0', '0', '아이엠', '1', '2', '2'),
('4050', '4E1K', '34', '0', '16', '0', '2024-12-30', '1', NULL, '아이엠', '0', '2', '2'),
('4051', '5Y4Y', '71', '1', NULL, '1', '2024-08-19', '1', '1', '아이엠', '0', '2', '2'),
('4052', '1U1U', '76', '0', '6', '1', '2025-01-13', '0', NULL, '아이엠', '1', '2', '2'),
('4053', '4Y7K', '85', '1', '5', '1', '2023-11-25', '0', '1', '아이엠', '0', '2', '2'),
('4054', '5C2U', '65', '0', '12', '1', '2024-06-06', '0', '1', '아이엠', '0', '2', '2'),
('4055', '4M3R', '64', '0', '6', '1', '2024-12-01', '1', '1', '아이엠', '0', '2', '2'),
('4056', '7N6S', '31', '1', '16', '0', '2024-09-12', '1', NULL, '아이엠', '2', '2', '2'),
('4057', '6I8G', '38', '1', '16', '1', '2024-02-18', '1', '1', '아이엠', '0', '2', '2'),
('5058', '1Q4L', '75', '1', '9', '0', '2023-11-15', '0', '1', 'Rt. hemiplegia d/t Lt. MCA infarction ', '0', '2', '2'),
('5059', '2U0Z', '0', '0', '12', '0', '2025-02-12', '0', '1', 'RT hemiplegia d/t Lt BG, F-P-O lobes infarction', '0', '0', '0'),
('5060', '7K5Q', '67', '0', '6', '0', '2024-11-11', '0', '1', 'Lt. hemiplegia d/t Cb. infarction with hemorrhagic transformation', '1', '2', '2'),
('5061', '8E3R', '63', '1', '6', '0', '2022-06-27', '1', '1', 'Tetraplegia d/t SAH, ICH in Lt. frontal lobe  ', '0,1', '2', '2'),
('5062', '8N9P', '77', '1', '0', '0', '2025-01-08', '0', '1', 'Rt. hemiplegia d/t Lt. BG infarction ', '0', '2', '2'),
('5063', '8Z5D', '68', '1', '12', '0', '2025-01-22', '1', '1', 'RT hemiplegia d/t ICH', '0', '2', '2'),
('5064', '0W0L', '73', '0', '12', '0', '2025-01-04', '0', '1', 'Rt. hemiplegia d/t Lt. cerebral infarction', '0', '2', '2'),
('5065', '4U1J', '67', '0', '14', '1', '2024-09-20', '0', '1', 'Rt.hemiplegia d/t Cb.infarction (Lt. BG & CR) ', '0', '2', '2'),
('5066', '3M6L', '58', '0', '9', '0', '2024-10-07', '1', '1', 'Rt.hemiplegia d/t ICH, IVH  ', '0', '2', '2'),
('5067', '5N8F', '47', '0', '12', '0', '2024-08-24', '0', '1', 'Lt hemiplegia d/t infarction', '1', '2', '2'),
('3068', '1X6A', '38', '0', '12', '0', '2023-07-20', '1', '1', 'Rt. hemiplegia d/t Lt. BG & CR ICH', '0', '2', '2'),
('3069', '0X9P', '60', '1', '12', '0', '2025-01-31', '1', '1', 'Quadriplegia d/t Lt. BG ICH (2025.1.31) & old ICH  ', '1', '2', '2'),
('3070', '7D6T', '67', '1', '6', '0', '2024-12-17', '1', NULL, 'Rt. hemiplegia and aphasia d/t cerebral ICH', '0', '2', '2'),
('3071', '1I2N', '67', '0', '6', '0', '2024-08-09', '0', '1', 'Rt. hemiplegia. aphasia. dysphagia d/t Lt. MCA infarction', '0', '2', '2'),
('3072', '3H5B', '42', '1', '14', '0', '2024-11-19', '1', '0', 'Left hemiplegia d/t Right BG ICH', '1', '2', '2'),
('3073', '0X6C', '65', '0', '6', '0', '2024-10-23', '0', '0', 'Lt hemiplegia d/t  Rt ant medullary infarction', '1', '2', '2'),
('3074', '1V6S', '53', '0', '12', '0', '2025-02-23', '1', '0', 'Rt. hemiplegia d/t cerebral ICH', '0', '2', '2'),
('3075', '0C2H', '62', '0', '14', '0', '2025-02-04', '0', '1', 'Gait disturbance d/t Left temporoparietal lobe infarction', '2', '2', '2'),
('3076', '1S7P', '69', '0', '12', '0', '2025-02-15', '0', '1', 'Rt. hemiplegia d/t Lt. PVWM infarction', '0', '2', '2'),
('1077', '8U9W', NULL, NULL, NULL, '1', NULL, NULL, NULL, '05068463', NULL, NULL, NULL),
('1078', '9P2E', '84', '0', '12', '1', '2025-01-20', NULL, NULL, '00202824', NULL, NULL, NULL),
('1079', '8U7T', '0', '0', '6', '0', '2025-01-15', NULL, NULL, '10599920', NULL, NULL, NULL);
/*!40000 ALTER TABLE `patient_info` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-08-22 12:56:31
