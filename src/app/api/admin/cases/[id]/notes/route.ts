import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const notes = await db.caseNote.findMany({
      where: { caseId: id },
      orderBy: { createdAt: 'desc' },
    });

    return NextResponse.json(notes);
  } catch (error) {
    console.error('Fetch notes error:', error);
    return NextResponse.json({ error: 'Failed to fetch notes' }, { status: 500 });
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const { text, isPinned } = body as { text?: string; isPinned?: boolean };

    if (!text || typeof text !== 'string' || text.trim().length === 0) {
      return NextResponse.json({ error: 'Text is required' }, { status: 400 });
    }

    const existing = await db.case.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json({ error: 'Case not found' }, { status: 404 });
    }

    const note = await db.caseNote.create({
      data: {
        caseId: id,
        text: text.trim(),
        isPinned: isPinned === true,
      },
    });

    return NextResponse.json(note, { status: 201 });
  } catch (error) {
    console.error('Create note error:', error);
    return NextResponse.json({ error: 'Failed to create note' }, { status: 500 });
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const { noteId, isPinned } = body as { noteId?: string; isPinned?: boolean };

    if (!noteId || typeof noteId !== 'string') {
      return NextResponse.json({ error: 'noteId is required' }, { status: 400 });
    }

    if (typeof isPinned !== 'boolean') {
      return NextResponse.json({ error: 'isPinned is required' }, { status: 400 });
    }

    const existing = await db.caseNote.findFirst({
      where: { id: noteId, caseId: id },
    });
    if (!existing) {
      return NextResponse.json({ error: 'Note not found' }, { status: 404 });
    }

    const updated = await db.caseNote.update({
      where: { id: noteId },
      data: { isPinned },
    });

    return NextResponse.json(updated);
  } catch (error) {
    console.error('Update note error:', error);
    return NextResponse.json({ error: 'Failed to update note' }, { status: 500 });
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const noteId = request.nextUrl.searchParams.get('noteId');

    if (!noteId) {
      return NextResponse.json({ error: 'noteId query parameter is required' }, { status: 400 });
    }

    const existing = await db.caseNote.findFirst({
      where: { id: noteId, caseId: id },
    });
    if (!existing) {
      return NextResponse.json({ error: 'Note not found' }, { status: 404 });
    }

    await db.caseNote.delete({ where: { id: noteId } });

    return NextResponse.json({ message: 'Note deleted' });
  } catch (error) {
    console.error('Delete note error:', error);
    return NextResponse.json({ error: 'Failed to delete note' }, { status: 500 });
  }
}
