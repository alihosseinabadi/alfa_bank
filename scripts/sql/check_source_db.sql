SELECT COUNT(*) AS table_count
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE';

SELECT 'Articles' AS table_name, COUNT(*) AS row_count
FROM public."Articles"
UNION ALL
SELECT 'Courses', COUNT(*)
FROM public."Courses"
UNION ALL
SELECT 'Documents', COUNT(*)
FROM public."Documents"
UNION ALL
SELECT 'Webinars', COUNT(*)
FROM public."Webinars"
UNION ALL
SELECT 'Podcasts', COUNT(*)
FROM public."Podcasts"
UNION ALL
SELECT 'CourseUserBindings', COUNT(*)
FROM public."CourseUserBindings"
UNION ALL
SELECT 'CourseUserLessonBindings', COUNT(*)
FROM public."CourseUserLessonBindings"
UNION ALL
SELECT 'UserRatings', COUNT(*)
FROM public."UserRatings";
