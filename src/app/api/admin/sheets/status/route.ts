import { NextResponse } from 'next/server';
import { getGoogleSheetsConfigStatus } from '@/lib/google-sheets';

export async function GET() {
  const status = getGoogleSheetsConfigStatus();
  return NextResponse.json(status);
}
