-- MySQL dump for table `patient_api_key`
-- 환자 ID별 API Key 보관 테이블

DROP TABLE IF EXISTS `patient_api_key`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `patient_api_key` (
  `PATIENT_ID` char(4) NOT NULL,
  `API_KEY` varchar(64) NOT NULL,
  `ISSUED_AT` datetime DEFAULT CURRENT_TIMESTAMP,
  `LAST_USED_AT` datetime DEFAULT NULL,
  PRIMARY KEY (`PATIENT_ID`),
  UNIQUE KEY `uk_api_key` (`API_KEY`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='환자별 API Key 보관';
/*!40101 SET character_set_client = @saved_cs_client */;

-- 초기 데이터 없음. 업로드 시 발급된 키를 여기 저장해 사용.

