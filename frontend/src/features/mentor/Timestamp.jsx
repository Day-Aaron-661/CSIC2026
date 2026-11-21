import React from 'react';

export default function Timestamp({ value, prefix }) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return null;
  return <span>{prefix} <time dateTime={value}>{date.toLocaleString()}</time></span>;
}
