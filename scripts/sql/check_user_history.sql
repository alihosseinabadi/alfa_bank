-- Read-only aggregate audit for the organizer archive. Never select IP or user IDs.
SELECT 'CourseUserBindings' AS source, count(*) AS rows, count(DISTINCT "UserId") AS users,
 count(*) FILTER(WHERE "BuyingDate" IS NOT NULL) AS buying_dates, count(*) FILTER(WHERE "IsPaid") AS paid_flags,
 count(*) FILTER(WHERE "Completed"<"Created") AS completion_before_creation
FROM "CourseUserBindings";
SELECT 'CourseUserLessonBindings' AS source, count(*) AS rows,
 count(*) FILTER(WHERE "Completed"<"Created") AS completion_before_creation
FROM "CourseUserLessonBindings";
SELECT 'UserRatings' AS source,count(*) AS rows,count(DISTINCT "UserId") AS users,
 count(*) FILTER(WHERE "UserId" IS NULL) AS missing_users,count(*) FILTER(WHERE "IsDeleted") AS deleted
FROM "UserRatings";
SELECT "EntityTypeId",count(*) AS rows,count(*) FILTER(WHERE "UserId" IS NOT NULL) AS with_user
FROM "UserRatings" GROUP BY "EntityTypeId";
SELECT "Status","ContentAccess",count(*) FROM "CourseUserBindings" GROUP BY 1,2 ORDER BY 1,2;
SELECT 'CourseUserBindings.Created' AS field,count(*) AS rows,
 count(*) FILTER(WHERE extract(day FROM "Created")=1 AND ("Created" AT TIME ZONE 'UTC')::time='12:00:00') AS month_precision
FROM "CourseUserBindings"
UNION ALL SELECT 'CourseUserLessonBindings.Completed',count(*),
 count(*) FILTER(WHERE extract(day FROM "Completed")=1 AND ("Completed" AT TIME ZONE 'UTC')::time='12:00:00')
FROM "CourseUserLessonBindings"
UNION ALL SELECT 'UserRatings.Created',count(*),
 count(*) FILTER(WHERE extract(day FROM "Created")=1 AND ("Created" AT TIME ZONE 'UTC')::time='12:00:00')
FROM "UserRatings";
SELECT count(*) AS invalid_course_lesson_links
FROM "CourseUserLessonBindings" p JOIN "CourseUserBindings" e ON e."Id"=p."CourseUserId"
WHERE NOT EXISTS(SELECT 1 FROM "CourseLessonBindings" b WHERE b."CourseId"=e."CourseId" AND b."LessonId"=p."LessonId");
SELECT count(*) AS rating_tag_links,count(*) FILTER(WHERE coalesce("Text",'')<>'') AS nonempty_text
FROM "UserRatingTagsBindings";
SELECT count(*) AS related_rows,count(*) FILTER(WHERE "CourseId" IS NOT NULL) AS course_id_present FROM "RecommendedItems";
