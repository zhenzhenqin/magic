const databaseName = 'fooddiary-demo-media'
const bucket = 'photos'

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(bucket)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function run<T>(mode: IDBTransactionMode, perform: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDatabase()
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(bucket, mode)
      const request = perform(tx.objectStore(bucket))
      tx.oncomplete = () => resolve(request.result)
      tx.onabort = () => reject(tx.error ?? request.error)
    })
  } finally {
    db.close()
  }
}

export const mediaRepository = {
  get: (id: string) => run<Blob | undefined>('readonly', store => store.get(id)),
  save: (id: string, photo: Blob) => run('readwrite', store => store.put(photo, id)),
  delete: (id: string) => run('readwrite', store => store.delete(id)),
  clear: () => run('readwrite', store => store.clear()),
}
