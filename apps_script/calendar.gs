function doGet() {
  var now = new Date();
  var startOfToday = new Date(now);
  startOfToday.setHours(0, 0, 0, 0);
  var endOfTomorrow = new Date(now);
  endOfTomorrow.setDate(endOfTomorrow.getDate() + 2);
  endOfTomorrow.setHours(0, 0, 0, 0);

  var cal = CalendarApp.getDefaultCalendar();
  var events = cal.getEvents(startOfToday, endOfTomorrow);

  var lines = [];
  for (var i = 0; i < events.length && i < 8; i++) {
    var e = events[i];
    var start = e.getStartTime();
    var title = e.getTitle().replace(/\|/g, '-');
    var allDay = e.isAllDayEvent();

    var dateStr;
    if (allDay) {
      dateStr = 'ALL DAY';
    } else {
      var h = start.getHours();
      var m = start.getMinutes();
      dateStr = (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
    }

    var dayLabel;
    var today = new Date(startOfToday);
    var tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    var eventDate = new Date(start);
    eventDate.setHours(0, 0, 0, 0);

    if (eventDate.getTime() === today.getTime()) {
      dayLabel = 'TODAY';
    } else {
      dayLabel = 'TMRW';
    }

    lines.push(dayLabel + '|' + dateStr + '|' + title);
  }

  if (lines.length === 0) {
    lines.push('NONE|--|No upcoming events');
  }

  var output = lines.join('\n');
  return ContentService.createTextOutput(output)
    .setMimeType(ContentService.MimeType.TEXT);
}
